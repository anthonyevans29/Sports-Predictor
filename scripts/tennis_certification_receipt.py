"""
THE TENNIS DATA CERTIFICATION RECEIPT (ARCHITECT 2026-11-05, addendum 261 items 0 and 2(c); 2026-11-06, addendum 269
items 1-3; addendum 284 item 1(b): "a certification receipt script on the pattern of the NBA's (served and stored
phases)"; lane tennis-market-only, #838). Read-only, on scripts/nba_certification_receipt.py's pattern. Two phases,
run in this order on the laptop:

  1. SERVED (the default; Kalshi's public market data only, opens NO database, no key): BEFORE the first
     `sync-matches --competition ATP` / `WTA` writes a mapped row. Per tour series, in this order:
       THE SERIES (the /series listing's entry for KXATPMATCH / KXWTAMATCH, every key as served, the
       contract_terms_url and the fee fields verbatim) ·
       THE LISTING (/markets under each of open, closed, settled, paged TO THE LAST PAGE: 269 item 3(d), a cursor left
       is a refusal) · STATUS AND RESULT WORDS AS SERVED ·
       THE CONTRACT TERMS, BEFORE THE MAP (269 item 3(c): "BEFORE the status map, the series' contract_terms_url
       (served in the listing's keys) is read and the clause on incomplete matches — retirement, walkover,
       suspension — QUOTED on the PR"): contract_terms_url verbatim, and every distinct rules_secondary and
       early_close_condition the markets serve, verbatim, with one rules_primary per result word; the PR quotes the
       clause from this console (no wording is typed by Code) ·
       THE MAP (269 item 3(b), kalshi_tennis.settle): the projection by our status, every event left SCHEDULED by
       its reason, the events refused as fixtures by their reason ·
       GAME COUNTS by the ticker's year (our int-style season; late-December events of the next tour season read as
       the ticker's year, an open item) · THE TIMES (the kickoff, open for a ruling: every served time key beside the
       ticker's date, and the open markets already past the stored kickoff) · NULLS · INTEGRITY (out-of-scope series
       never read).
  2. STORED (--db COPY, no network): after the first syncs, on a .backup copy outside data/ opened
     mode=ro&immutable=1 (the NBA receipt's guards): counts per season by stored status, status_raw as stored, the
     settlement's truth (FINISHED with a winner and its settlement kept; SETTLED_SCALAR with no winner and its
     fraction kept), the scores null by ruling (269 item 2: "NULL AND LABELLED"), the players stored.

Exit: 0 every read answered; 1 a call failed; 2 a read REFUSED (a cursor left, a repeated cursor, a series the listing
does not serve, a --db that is not a fresh copy outside data/). Last line: TENNIS-CERTIFICATION-RECEIPT {json}
(counts only). Writes nothing (law 5: no file, no database; --db is opened read-only and immutable).

    python3 scripts/tennis_certification_receipt.py [--tour ATP --tour WTA]
    python3 scripts/tennis_certification_receipt.py --db /path/to/backup-copy.db
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# the adapter's pure readers and the schema's enums only: nothing here opens the database
from src.adapters import kalshi_tennis as kt  # noqa: E402
from src.db.schema import MatchStatus  # noqa: E402

OK, FAILED, REFUSED = 0, 1, 2
SIDECARS = ("-wal", "-shm", "-journal")
TAIL = "TENNIS-CERTIFICATION-RECEIPT"
TERMS_KEYS = ("rules_secondary", "early_close_condition")       # printed verbatim, every distinct value
FEE_KEYS = ("fee_type", "fee_multiplier")                       # the listing's fee fields, as the NBA receipt read them
MAX_DISTINCT = 25                                               # distinct texts printed per key; the rest counted
# THE TIMES: the time keys the stage-1 digest lists among those served (#838 issuecomment-6690719842, K3 "keys
# served"), printed beside the ticker's date so the kickoff can be ruled on a receipt (kalshi_tennis's THE KICKOFF)
TIME_KEYS = ("occurrence_datetime", "open_time", "close_time", "expected_expiration_time", "expiration_time",
             "latest_expiration_time")
TIME_SAMPLE = 12                                                # open markets printed with every time key


def ts(x):
    """A served time (ISO, 'Z' or an offset) as naive UTC, else None. Read only for the offsets the receipt prints."""
    if not isinstance(x, str) or not x:
        return None
    try:
        d = datetime.fromisoformat(x.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d


def v(x) -> str:
    return json.dumps(x, default=str, ensure_ascii=False)


def counts(c: Counter) -> str:
    return " · ".join(f"{k}: {n}" for k, n in sorted(c.items(), key=lambda kv: (-kv[1], str(kv[0])))) or "none"


def series_entry(get, series: str) -> tuple[dict | None, str]:
    """(the /series listing's entry whose ticker is `series` exactly, how it was read). The listing as
    KalshiAdapter.find_series reads it: category Sports first, else unfiltered. A listing that serves a cursor and not
    the series: REFUSED (the entry may be on a page not read)."""
    for params in ({"category": "Sports"}, {}):
        data = get("series", params)
        rows = data.get("series") if isinstance(data, dict) else None
        if not rows:
            continue
        hit = [s for s in rows if isinstance(s, dict) and s.get("ticker") == series]
        if len(hit) == 1:
            return hit[0], f"GET /series {params or '(no filter)'}"
        if len(hit) > 1:
            raise kt.Refused(f"REFUSED: the /series listing serves {series} {len(hit)} times; none is picked")
        if data.get("cursor"):
            raise kt.Refused(f"REFUSED: {series} is not on the /series listing's first page and a cursor is served")
    raise kt.Refused(f"REFUSED: the /series listing does not serve {series}")


def tour_report(tour: str, adapter, get, say) -> tuple[int, dict]:
    series = kt.SERIES[tour]
    out: dict = {"series": series}
    say(f"\n{tour} · {series}")
    # 1. THE SERIES ------------------------------------------------------------------------------------------------
    try:
        entry, how = series_entry(get, series)
    except kt.Refused as e:
        say(f"  {e}")
        return REFUSED, {**out, "refused": str(e)}
    say(f"  THE SERIES ({how}): keys served: {', '.join(sorted(entry))}")
    for k in ("title", "category", "tags", "frequency", *FEE_KEYS):
        say(f"    {k}: {v(entry.get(k, '<not served>'))}")
    terms_url = entry.get("contract_terms_url", "<not served>")
    say(f"    contract_terms_url: {v(terms_url)}")
    say(f"    contract_url: {v(entry.get('contract_url', '<not served>'))}")
    out["contract_terms_url_served"] = terms_url != "<not served>"
    # 2. THE LISTING -----------------------------------------------------------------------------------------------
    try:
        lst = adapter.listing(tour)
    except kt.Refused as e:
        say(f"  {e}")
        return REFUSED, {**out, "refused": str(e)}
    say(f"  THE LISTING (/markets, each status to its last page): {lst.markets} markets · pages {v(lst.pages)}")
    say(f"  STATUS WORDS AS SERVED: {counts(lst.status_words)}"
        + (f" · NOT IN THE RECEIPT'S WORDS {kt.STATUS_WORDS}: "
           f"{counts(Counter({k: n for k, n in lst.status_words.items() if k not in kt.STATUS_WORDS}))}"
           if set(lst.status_words) - set(kt.STATUS_WORDS) else ""))
    say(f"  RESULT WORDS AS SERVED: {counts(lst.result_words)}")
    # 3. THE CONTRACT TERMS, BEFORE THE MAP -------------------------------------------------------------------------
    markets = [m for fx in lst.fixtures for m in fx.markets]
    say("  THE CONTRACT TERMS (addendum 269 item 3(c); read BEFORE the map; quoted on the PR from this console)")
    say(f"    contract_terms_url (the series listing): {v(terms_url)}")
    for key in TERMS_KEYS:
        dist = Counter(m.get(key) if key in m else "<not served>" for m in markets)
        say(f"    {key}: {len(dist)} distinct value(s) over {len(markets)} markets (of the accepted events)")
        for val, n in sorted(dist.items(), key=lambda kv: -kv[1])[:MAX_DISTINCT]:
            say(f"      [{n}] {v(val)}")
        if len(dist) > MAX_DISTINCT:
            say(f"      ... {len(dist) - MAX_DISTINCT} more distinct value(s), not printed")
    for word in kt.RESULT_WORDS:
        one = next((m for m in markets if m.get("result") == word), None)
        if one is not None:
            say(f"    rules_primary, one market with result {word!r} ({one.get('ticker')}): {v(one.get('rules_primary'))}")
    say(f"    NOT QUOTED IN CODE: kalshi_tennis.CONTRACT_TERMS_QUOTE is {v(kt.CONTRACT_TERMS_QUOTE)} "
        "(the map below reads the result word only and infers nothing about retirement, walkover or suspension)")
    # 4. THE MAP ---------------------------------------------------------------------------------------------------
    say("  THE MAP (addendum 269 item 3(b)): 'yes' / 'no' on two 'finalized' markets, expiration_value the 'yes' "
        "market's player -> FINISHED, that player the winner · 'scalar' on both, 'finalized' -> SETTLED_SCALAR, no "
        "winner, the fraction kept · '' -> not settled (SCHEDULED) · anything else SCHEDULED, counted (law 4)")
    proj = Counter(fx.settlement.status.name for fx in lst.fixtures)
    why = Counter(fx.settlement.why for fx in lst.fixtures if fx.settlement.why)
    say(f"    projected: {counts(proj)}")
    say(f"    left SCHEDULED, by reason: {counts(why)}")
    for fx in lst.fixtures:
        if fx.settlement.why:
            say(f"      {fx.event}: {fx.settlement.why} · status {fx.settlement.status_raw} · results "
                f"{v([m.get('result') for m in fx.markets])}")
    scal = [fx for fx in lst.fixtures if fx.settlement.status == MatchStatus.SETTLED_SCALAR]
    vals = Counter(str(s.get("settlement_value_dollars")) for fx in scal for s in fx.settlement.served.values())
    say(f"    SETTLED_SCALAR events: {len(scal)} · their markets' settlement values: {sum(vals.values())} kept, "
        f"{len(vals)} distinct (kept verbatim on the row's external_ids['kalshi_settlement'])")
    say(f"    refused as fixtures, by reason: {counts(lst.refused)}")
    for ev, r in sorted(lst.refused_events.items()):
        say(f"      {ev}: {r}")
    # 5. GAME COUNTS -----------------------------------------------------------------------------------------------
    by_year = defaultdict(Counter)
    for fx in lst.fixtures:
        by_year[str(fx.day.year)][fx.settlement.status.name] += 1
    say("  GAME COUNTS (accepted events, by the ticker's year: our int-style season; OPEN: no ruling names a tennis "
        "season, so a late-December event of the next tour season reads as the ticker's year)")
    for y in sorted(by_year):
        say(f"    {y}: {sum(by_year[y].values())} · {counts(by_year[y])}")
    # 5b. THE TIMES (the kickoff, open for a ruling) ---------------------------------------------------------------
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    say(f"  THE TIMES (the kickoff is OPEN for a ruling; stored now: {kt.KICKOFF_LABEL}); offsets in hours from 00:00 "
        "UTC of the ticker's date")
    day_of = {m.get("ticker"): fx.day for fx in lst.fixtures for m in fx.markets}
    times_out = {}
    for key in TIME_KEYS:
        served = [m for m in markets if key in m]
        offs = Counter()
        for m in served:
            t, d = ts(m.get(key)), day_of.get(m.get("ticker"))
            if t is not None and d is not None:
                offs[round((t - datetime(d.year, d.month, d.day)).total_seconds() / 3600)] += 1
        say(f"    {key}: served on {len(served)} of {len(markets)} markets · offsets (h: markets) "
            + (" · ".join(f"{h:+d}: {n}" for h, n in sorted(offs.items(), key=lambda kv: -kv[1])[:10]) or "none"))
        times_out[key] = len(served)
    live = [(fx, m) for fx in lst.fixtures for m in fx.markets if str(m.get("status")) == "active"]
    past = [m.get("ticker") for fx, m in live if kt.kickoff_utc(fx.day) <= now]
    say(f"    active markets: {len(live)} · already past the stored kickoff at this run (the capture refuses them as "
        f"in play): {len(past)}")
    for fx, m in live[:TIME_SAMPLE]:
        say(f"      {m.get('ticker')} · ticker date {fx.day} · stored kickoff {kt.kickoff_utc(fx.day):%Y-%m-%d %H:%M}Z · "
            + " · ".join(f"{k} {v(m.get(k, '<not served>'))}" for k in TIME_KEYS))
    if len(live) > TIME_SAMPLE:
        say(f"      ... {len(live) - TIME_SAMPLE} more active market(s), not printed")
    # 6. NULLS -----------------------------------------------------------------------------------------------------
    no_winner = [fx.event for fx in lst.fixtures if fx.settlement.status == MatchStatus.FINISHED and not fx.settlement.winner]
    say("  NULLS")
    say(f"    FINISHED with no winner: {len(no_winner)} (must read 0)")
    say(f"    {kt.SCORES_NULL_LABEL}: every row")
    say(f"    {kt.KICKOFF_LABEL}")
    # 7. INTEGRITY -------------------------------------------------------------------------------------------------
    names = defaultdict(set)
    for fx in lst.fixtures:
        for nm in (fx.home, fx.away):
            names[nm.casefold()].add(nm)
    cased = {k: sorted(s) for k, s in names.items() if len(s) > 1}
    say("  INTEGRITY")
    say(f"    players: {len(names)} · spelled in more than one letter case (one player, 238 item 2(b)): {len(cased)}"
        + (": " + "; ".join(" / ".join(s) for s in list(cased.values())[:10]) if cased else ""))
    say(f"    out-of-scope series read: none (the two tour series only, 269 item 3(f); {len(kt.OUT_OF_SCOPE)} named "
        "out of scope in kalshi_tennis.OUT_OF_SCOPE)")
    out.update(markets=lst.markets, pages=lst.pages, events=len(lst.fixtures), projected=dict(proj),
               scheduled_why=dict(why), refused=dict(lst.refused), status_words=dict(lst.status_words),
               result_words=dict(lst.result_words), finished_no_winner=len(no_winner), players=len(names),
               by_year={y: dict(c) for y, c in by_year.items()}, time_keys_served=times_out,
               active=len(live), active_past_kickoff=len(past))
    return OK, out


def served_phase(tours: list[str], adapter, say) -> tuple[int, dict]:
    say(f"TENNIS DATA CERTIFICATION RECEIPT · SERVED (addenda 261 item 2(c), 269 items 1-3, 284 item 1(b); #838) · "
        f"read-only · opens no database · no key · {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    say("  run BEFORE the first `sync-matches --competition ATP` / `WTA`: the contract terms are read before the map")
    worst, out = OK, {"tours": {}}
    for tour in tours:
        try:
            code, rep = tour_report(tour, adapter, adapter._get, say)
        except Exception as e:                  # noqa: BLE001 - a failed read is reported, never raised
            say(f"  FAILED: {tour}: {type(e).__name__}: {e}")
            code, rep = FAILED, {"failed": type(e).__name__}
        worst = max(worst, code)
        out["tours"][tour] = rep
    say(f"\nCALLS: {adapter.calls} this run (Kalshi public market data; no key)")
    out["calls"] = adapter.calls
    return worst, out


def stored_phase(db: str, tours: list[str], say) -> tuple[int, dict]:
    import sqlite3

    from src.walters import mlb_pitchers_gate as mp
    try:
        path = mp.check_db(db)
        for sc in SIDECARS:
            if path.with_name(path.name + sc).exists():
                raise mp.GateRefused(f"--db {db} has a {sc} sidecar ({path.name + sc}): not a fresh .backup copy; "
                                     "immutable=1 would ignore it and read a stale file; take a fresh .backup copy")
        con = mp.open_ro(path)
    except mp.GateRefused as e:
        say(f"REFUSED: {e}; nothing read")
        return REFUSED, {"refused": str(e)}
    say(f"TENNIS DATA CERTIFICATION RECEIPT · STORED (addendum 261 item 0: counts per season, status mapping, true-zero "
        f"nulls) · --db {path} (a .backup copy, opened {mp.COPY_URI_QUERY.lstrip('?')}) · no network")
    names = {s.name for s in MatchStatus}
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        rows = con.execute(
            "SELECT m.id, m.season, m.status, m.status_raw, m.utc_date, m.home_score, m.away_score, "
            "m.full_time_result, m.external_ids, c.code, c.sport FROM matches m JOIN competitions c "
            "ON c.id = m.competition_id WHERE c.code IN (%s)" % ",".join("?" * len(tours)), tuple(tours)).fetchall()
        players = con.execute("SELECT COUNT(*) FROM teams WHERE sport = 'TENNIS'").fetchone()[0]
    except sqlite3.Error as e:
        say(f"REFUSED: --db {path}: cannot be read as the schema the receipt needs ({type(e).__name__}: {e})")
        return REFUSED, {"refused": "schema"}
    finally:
        con.close()
    say(f"  players stored (teams of sport TENNIS): {players}")
    out: dict = {"players": players, "tours": {}}

    def ext(r):
        x = r[8]
        try:
            return json.loads(x) if isinstance(x, str) else (x or {})
        except ValueError:
            return {}
    for tour in tours:
        rs = [r for r in rows if r[9] == tour]
        say(f"\n{tour} (stored): {len(rs)} rows · sport {counts(Counter(r[10] for r in rs))}")
        by_season = defaultdict(list)
        for r in rs:
            by_season[str(r[1])].append(r)
        rep: dict = {"rows": len(rs), "seasons": {}}
        for season in sorted(by_season):
            ss = by_season[season]
            st = Counter(r[2] for r in ss)
            odd = {k: n for k, n in st.items() if k not in names}
            say(f"  {season}: {len(ss)} rows · by status: {counts(Counter({k: n for k, n in st.items() if k in names}))}"
                + (f" · UNRECOGNISED stored values: {counts(Counter(odd))}" if odd else ""))
            say(f"    status_raw (the served words kept): {counts(Counter(r[3] if r[3] is not None else '<none>' for r in ss))}")
            fin = [r for r in ss if r[2] == MatchStatus.FINISHED.name]
            scal = [r for r in ss if r[2] == MatchStatus.SETTLED_SCALAR.name]
            checks = {
                "FINISHED with no winner": [r[0] for r in fin if r[7] not in ("HOME", "AWAY")],
                "FINISHED with no settlement kept": [r[0] for r in fin if not ext(r).get("kalshi_settlement")],
                "SETTLED_SCALAR carrying a winner": [r[0] for r in scal if r[7] is not None],
                "SETTLED_SCALAR with no settlement kept": [r[0] for r in scal if not ext(r).get("kalshi_settlement")],
                "a score stored (NULL AND LABELLED by 269 item 2)": [r[0] for r in ss if r[5] is not None or r[6] is not None],
                "no event ticker under kalshi_tennis": [r[0] for r in ss if not ext(r).get(kt.SOURCE)],
            }
            for label, ids in checks.items():
                say(f"    {label}: {len(ids)} (must read 0: TRUE ZERO)" + (f": match {', '.join(map(str, ids[:20]))}" if ids else ""))

            def utc(x):
                return datetime.fromisoformat(str(x)[:19]) if x else None
            late = [r[0] for r in ss if r[2] == MatchStatus.SCHEDULED.name and utc(r[4]) and utc(r[4]) < now - timedelta(days=2)]
            say(f"    SCHEDULED with a stored kickoff more than 2 days before this run (unsettled, or settled after "
                f"the chain's window): {len(late)}")
            rep["seasons"][season] = {"rows": len(ss), "by_status": dict(st), "late_scheduled": len(late),
                                      **{k: len(i) for k, i in checks.items()}}
        out["tours"][tour] = rep
    return OK, out


def main(argv=None, adapter=None) -> int:
    ap = argparse.ArgumentParser(description="Tennis data certification receipt (addenda 269, 284 item 1(b))")
    ap.add_argument("--tour", action="append", default=None, choices=list(kt.SERIES),
                    help="ATP and/or WTA (repeatable; default both)")
    ap.add_argument("--db", default=None, help="STORED phase: a .backup copy outside data/ (no network)")
    a = ap.parse_args(argv)
    tours = a.tour or list(kt.SERIES)
    lines: list[str] = []

    def say(line: str = "") -> None:
        lines.append(str(line))
        print(line, flush=True)

    if a.db is not None:
        code, out = stored_phase(a.db, tours, say)
        phase = "stored"
    else:
        adapter = adapter or kt.KalshiTennisAdapter()
        code, out = served_phase(tours, adapter, say)
        phase = "served"
    print(f"{TAIL} " + json.dumps({"phase": phase, "exit": code, **out}, default=str, sort_keys=True), flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
