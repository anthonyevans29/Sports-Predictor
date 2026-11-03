"""
THE SHARED MATCHER'S PAIR, BEFORE AND AFTER (#413; ARCHITECT 2026-11-03 09:00 ET, addendum 230 item 0(a)), READ-ONLY.

The ruling, verbatim (addendum 230 item 0(a)): "#413, THE SHARED KALSHI MATCHER (one team name places a market; markets
land on other games; found on the college files, the mechanism on the shared path of all four series) — FIX NOW, its
own PR: the pair comes from the event's sibling markets as the soccer path does since 09-13; the yes-team fallback
goes; a market whose pair cannot be formed is REFUSED by the sentinel (never placed by one name); a read-only receipt
over the stored snapshots (the ids of 44 item 2's receipt: 32749, 32763, 32810, the UGAALA split) shows each now
refused or placed on both names. Gate-class by contract (the K-track's placement) — the PR body quotes the
before/after receipt. Size M."

WHAT IT READS (each reading the conservative one, law 4):
- THE SELECTION: the stored Kalshi legs (odds_snapshots, source 'kalshi', with a market_ticker) on the --match-ids
  games, and every stored leg of --events; then every stored leg of each event so found, on any game, so an event
  split across two games shows both. Match ids are machine-local: the defaults are the laptop's, the ids of addendum
  44 item 2's receipt (32749, 32763, 32810) and of addendum 37's (32747, 32812, 32772, 32738); the events (the
  ticker less its last '-' part, walters/kalshi_legs.event_of's rule) are the same on every machine, and the default
  is the nine KXNCAAFGAME 2026-10-10 events of addendum 37's receipt, the UGAALA split among them.
- BEFORE: what is stored, per event: each leg (selection, ticker) and the game it sits on (match id, away @ home, our
  kickoff), with its capture count and its first and last capture.
- AFTER: what the shared matcher (src/ingestion/kalshi_match.place, the one placement of both sync paths) decides for
  the event's markets, re-run on what the store holds: the event's sibling markets are the rows of
  kalshi_settled_markets (written by kalshi-history alone) of that event, each with its ticker and its yes_sub_title.
  A snapshot carries no name, no title and no sibling (law 1: odds_snapshots stores match_id, selection and the
  ticker), so an event with no settled row is printed "pair not formable from the store: refused" and is never placed
  here; a stored leg whose ticker has no settled row is printed "not in the settled store: its name is not stored".
  The title is not stored, so the two-name title fallback (kalshi_match._names) never reads here: the pair is the
  siblings' or nothing. Placement is kalshi_history.place_events (km.place per event on the stored games of the
  series' own competition on the event's days, kalshi_sync.stored_games; now = EPOCH, the window unbounded) over
  EVERY settled event of the series in the copy, never only the selection, so the claims rule ("two markets claim one
  side of one game") reads across them as kalshi-history's run reads every event it knows of and a verdict does not
  depend on --events; the identity hold (kalshi_history.identity_holds) over the same events, with no open list (a
  copy holds none: nothing is held for being open); a row placed by ruling (kalshi_history.RULED_NOTE) read by its
  stored side, never placed by date (place_events' `stored`, as the run reads it). Not read here, each a run's: its
  --since/--until range, its window and in-play read (a live sync refuses OUTSIDE_WINDOW or IN_PLAY where this places,
  and never places on another game), the exchange's open list, and a NEW market's claims against a stored row's side
  (a stored row is never placed again). The header prints the scope per series. Beside it, kalshi-history's own
  stored decision of each settled row (match_id and side, or its note), as held.
- Per stored leg, the verdict: "stored on its own game: placed here on both names" (the matcher places that ticker on
  the game and side it is stored on), "stored on its own game, WRONG SIDE: placed here SIDE on both names" (the right
  game, the other side), "stored on ANOTHER game: placed on match N SIDE on both names" (the stored leg sits on a game
  the matcher never gives it: the stored leg is wrong, and stays stored as history), "refused: <reason>" or "pair not
  formable from the store: refused"; "by ruling" in place of "on both names" for a row placed by ruling. Each verdict
  has its own count.

--db: a .backup copy outside the repo's data/ (mlb_pitchers_gate.check_db: the checkout's data/, and the main
checkout's from a worktree, by path or identity; never the app's configured database; an existing file, never
created), refused with a -wal / -shm / -journal beside it (nfl_v2_gate.check_db's rule: immutable=1 would ignore it),
opened mode=ro&immutable=1 (addendum 198 item 6(ii); mlb_pitchers_gate.readonly_session). Refusals exit 2, nothing
read. No network. Writes nothing: no row, no file.

Last line: KALSHI-PAIR-RECEIPT {json} (counts only).

    python3 scripts/kalshi_pair_receipt.py --db COPY [--match-ids 32749,32763,...] [--events KXNCAAFGAME-26OCT10UGAALA,...]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REFUSED = 2
SIDECARS = ("-wal", "-shm", "-journal")      # nfl_v2_gate.check_db's rule: immutable=1 would ignore each of them
# addendum 44 item 2's receipt (32749, 32763, 32810: the laptop's ids), then addendum 37's rows of it
DEFAULT_MATCH_IDS = (32749, 32763, 32810, 32747, 32812, 32772, 32738)
DEFAULT_EVENTS = tuple(f"KXNCAAFGAME-26OCT10{e}" for e in (
    "UGAALA", "KUUTAH", "HOUKSU", "FAMUALST", "UNDUNI", "NDSUUNLV", "CCARMRSH", "SCSTCHSO", "COOKAAMU"))
NOT_FORMABLE = "pair not formable from the store: refused"
NOT_STORED = "not in the settled store: its name is not stored"
OWN = "stored on its own game: placed here {how}"
WRONG_SIDE = "stored on its own game, WRONG SIDE: placed here {side} {how}"
OTHER = "stored on ANOTHER game: placed on match {mid} {side} {how}"
RULING_230_0A = ("#413, THE SHARED KALSHI MATCHER (one team name places a market; markets land on other games; found on "
                 "the college files, the mechanism on the shared path of all four series) — FIX NOW, its own PR: the "
                 "pair comes from the event's sibling markets as the soccer path does since 09-13; the yes-team "
                 "fallback goes; a market whose pair cannot be formed is REFUSED by the sentinel (never placed by one "
                 "name); a read-only receipt over the stored snapshots (the ids of 44 item 2's receipt: 32749, 32763, "
                 "32810, the UGAALA split) shows each now refused or placed on both names. Gate-class by contract (the "
                 "K-track's placement) — the PR body quotes the before/after receipt. Size M.")


class Refused(Exception):
    """A refusal: printed as REFUSED, exit 2."""


def event_of(ticker) -> str | None:
    """The ticker less its last '-' part (walters/kalshi_legs.event_of's rule, #414)."""
    t = str(ticker or "")
    return t.rsplit("-", 1)[0] if "-" in t else None


def series_of(ticker) -> str | None:
    return str(ticker).split("-", 1)[0] if ticker else None


def _ids(text: str) -> tuple[int, ...]:
    try:
        out = tuple(int(x) for x in text.split(",") if x.strip())
    except ValueError:
        raise Refused(f"--match-ids {text!r}: not a comma-separated list of integers")
    return out


def _events(text: str) -> tuple[str, ...]:
    out = tuple(x.strip() for x in text.split(",") if x.strip())
    bad = [e for e in out if event_of(e) is None]
    if bad:
        raise Refused(f"--events: {', '.join(bad)} is not an event ticker (SERIES-STAMP)")
    return out


def _columns(s, table: str) -> set:
    from sqlalchemy import text
    return {r[1] for r in s.execute(text(f"PRAGMA table_info({table})"))}


def _game_text(g) -> str:
    if g is None:
        return "no such match in this copy"
    ko = g["kickoff"]
    return f"{g['away']} @ {g['home']} · our kickoff {str(ko)[:16]}Z"


def collect(s, match_ids, events) -> dict:
    """Pure over the read-only session: the BEFORE legs, the settled siblings, the AFTER placement, the verdicts."""
    from sqlalchemy import select, text

    from src.adapters.kalshi import KalshiAdapter
    from src.db.schema import Competition
    from src.ingestion import kalshi_history as kh
    from src.ingestion import kalshi_match as km
    from src.ingestion.kalshi_sync import stored_games

    cols = _columns(s, "odds_snapshots")
    if not cols:
        raise Refused("odds_snapshots does not exist in this copy: no stored leg to read")
    if "market_ticker" not in cols:
        raise Refused("odds_snapshots.market_ticker does not exist (migrate_kalshi_ticker.py not run): no stored leg "
                      "can be keyed by its event")
    legs_sql = ("SELECT s.match_id, s.selection, s.market_ticker, s.captured_at FROM odds_snapshots s "
                "WHERE s.source = 'kalshi' AND s.market_ticker IS NOT NULL AND s.market_ticker != ''")
    rows = s.execute(text(legs_sql)).all()
    wanted_events, ids = set(events), set(match_ids)
    for mid, _sel, tic, _cap in rows:
        if mid in ids and event_of(tic):
            wanted_events.add(event_of(tic))
    # BEFORE: (event) -> (match, selection, ticker) -> [captures]
    before: dict = defaultdict(lambda: defaultdict(list))
    for mid, sel, tic, cap in rows:
        ev = event_of(tic)
        if ev in wanted_events:
            before[ev][(mid, sel, tic)].append(str(cap))
    def games_of(mids) -> dict:
        if not mids:
            return {}
        q = text("SELECT m.id, m.utc_date, COALESCE(h.name, '?'), COALESCE(a.name, '?') FROM matches m "
                 "LEFT JOIN teams h ON h.id = m.home_team_id LEFT JOIN teams a ON a.id = m.away_team_id "
                 f"WHERE m.id IN ({','.join(str(int(m)) for m in sorted(mids))})")
        return {r[0]: {"match_id": r[0], "kickoff": r[1], "home": r[2], "away": r[3]} for r in s.execute(q)}

    games = games_of({k[0] for legs in before.values() for k in legs} | set(match_ids))
    # the settled rows (kalshi-history's), as held: the siblings of each event read, and every event of its series
    settled_ok = "ticker" in _columns(s, kh.TABLE)
    sibs: dict = defaultdict(list)
    series_rows: dict = defaultdict(lambda: defaultdict(list))      # series -> event -> its settled rows
    if settled_ok:
        q = text(f"SELECT ticker, event_ticker, series, yes_sub_title, match_id, side, notes FROM {kh.TABLE}")
        for t, e, ser, yst, mid, side, notes in s.execute(q):
            ev = e or event_of(t)
            r = {"ticker": t, "event_ticker": ev, "series": ser, "yes_sub_title": yst, "match_id": mid, "side": side,
                 "notes": notes}
            series_rows[ser or series_of(ev)][ev].append(r)
            if ev in wanted_events:
                sibs[ev].append(r)
    # AFTER: per series, the matcher over EVERY settled event of the series in this copy (never only the selection:
    # the claims rule reads across them, as kalshi-history's run reads every event it knows of), on the stored games
    # of the series' own competition (kalshi_history.place_events); the identity hold over the same events (no open
    # list in a copy: nothing is held for being open); a row placed by ruling read by its stored side, as the run
    # reads it (place_events' `stored`)
    after: dict = {}
    lines: list = []
    names: dict = {}
    scope: dict = {}
    by_series: dict = defaultdict(list)
    for ev in sorted(wanted_events):
        if sibs.get(ev):
            by_series[series_of(ev)].append(ev)
    for ser, evs in sorted(by_series.items()):
        comp, soccer = kh.competition_for(ser, KalshiAdapter)
        is_tie = KalshiAdapter.is_tie_market if soccer else (lambda m: False)
        rows_of = series_rows.get(ser) or {ev: sibs[ev] for ev in evs}
        markets = [{"ticker": r["ticker"], "event_ticker": ev, "yes_sub_title": r["yes_sub_title"], "title": ""}
                   for ev in sorted(rows_of) for r in rows_of[ev]]
        for ev in evs:
            names[ev] = [n for n in dict.fromkeys((r["yes_sub_title"] or "").strip() for r in sibs[ev]
                                                  if not is_tie({"ticker": r["ticker"],
                                                                 "yes_sub_title": r["yes_sub_title"]})) if n]
        comp_id = (s.execute(select(Competition.id).where(Competition.code == comp)).scalar_one_or_none()
                   if comp else None)
        scope[ser] = {"events": len(rows_of), "markets": len(markets), "held": 0, "ruled": 0}
        if comp_id is None:
            for mk in markets:
                after[mk["ticker"]] = ("refused", f"no competition for {ser} in this copy ({comp or 'unmapped'})")
            continue
        ruled = {r["ticker"]: (r["match_id"], r["side"]) for ev in rows_of for r in rows_of[ev]
                 if r["match_id"] is not None and kh.RULED_NOTE in (r["notes"] or "")}
        known = {}
        for mk in markets:
            known.setdefault(mk["event_ticker"], []).append(mk)
        targets = {ev for ev, mks in known.items() if km.ticker_stamp(mks[0])[1] is not None}
        holds = (kh.identity_holds(targets, known, set(), lambda mks: stored_games(s, [comp_id], mks), is_tie)
                 if targets else {})
        scope[ser]["held"], scope[ser]["ruled"] = len(holds), len(ruled)
        day_games = stored_games(s, [comp_id], markets)
        placed, why, ln = kh.place_events(markets, day_games, is_tie, holds, frozenset(ruled))
        lines.extend(x for x in ln if any(ev in x for ev in evs))
        by_id = {g.id: g for g in day_games}
        for mk in markets:
            t = mk["ticker"]
            if t in ruled:
                after[t] = ("ruled",) + ruled[t]
            elif t in placed:
                after[t] = ("placed", placed[t][0], placed[t][2])
            else:
                after[t] = ("refused", why.get(t, "not placed"))
            if after[t][0] != "refused" and after[t][1] not in games and after[t][1] in by_id:
                g = by_id[after[t][1]]
                games[g.id] = {"match_id": g.id, "kickoff": g.utc_date, "home": g.home_team.name,
                               "away": g.away_team.name}
    # a ruled row's game can lie outside the events' days: read it by its id
    games.update(games_of({a[1] for a in after.values() if a[0] == "ruled" and a[1] not in games}))
    # the verdict per stored leg: (its count key, its words)
    verdicts = {}
    for ev, legs in before.items():
        for (mid, sel, tic) in legs:
            a = after.get(tic)
            if not sibs.get(ev):
                verdicts[(mid, sel, tic)] = ("not_formable", NOT_FORMABLE)
            elif a is None:
                verdicts[(mid, sel, tic)] = ("not_stored", NOT_STORED)
            elif a[0] == "refused":
                verdicts[(mid, sel, tic)] = ("refused", f"refused: {a[1]}")
            else:
                how = "by ruling" if a[0] == "ruled" else "on both names"
                if (a[1], a[2]) == (mid, sel):
                    verdicts[(mid, sel, tic)] = ("own_game", OWN.format(how=how))
                elif a[1] == mid:
                    verdicts[(mid, sel, tic)] = ("own_game_wrong_side", WRONG_SIDE.format(side=a[2], how=how))
                else:
                    verdicts[(mid, sel, tic)] = ("another_game", OTHER.format(mid=a[1], side=a[2], how=how))
    return {"before": before, "games": games, "sibs": sibs, "after": after, "names": names, "lines": lines,
            "verdicts": verdicts, "events": sorted(wanted_events), "match_ids": list(match_ids),
            "settled_table": settled_ok, "scope": scope}


def _after_text(a, games) -> str:
    if a[0] == "placed":
        return f"placed on match {a[1]} {a[2]} ({_game_text(games.get(a[1]))})"
    if a[0] == "ruled":
        return (f"placed by ruling on match {a[1]} {a[2]} ({_game_text(games.get(a[1]))}): its stored side, never "
                "placed by date")
    return f"refused: {a[1]}"


def _stored_text(r) -> str:
    if r["match_id"] is not None:
        return f"kalshi-history stored: match {r['match_id']} {r['side']}"
    return f"kalshi-history stored: no match ({r['notes'] or 'no note'})"


def report(c: dict, db_text: str, echo=print) -> dict:
    echo("THE SHARED MATCHER'S PAIR, BEFORE AND AFTER (#413; addendum 230 item 0(a)) — read-only")
    echo(f"  source: {db_text}")
    echo(f"  match ids (machine-local): {', '.join(str(m) for m in c['match_ids']) or 'none'}")
    echo(f"  events read: {len(c['events'])}" + ("" if c["settled_table"] else
         " · kalshi_settled_markets is not in this copy: no event's pair can be formed from the store"))
    echo("  after = kalshi_match.place on the store's siblings (kalshi_settled_markets: ticker, yes_sub_title), "
         "kalshi_history.place_events: now = EPOCH, window unbounded; the title is not stored")
    for ser, sc in sorted(c["scope"].items()):
        echo(f"  after's scope, {ser}: every settled event of the series in this copy ({sc['events']} events, "
             f"{sc['markets']} markets), the claims rule across them; identity holds over them: {sc['held']} held "
             f"(no open list in a copy: none held for being open); {sc['ruled']} row(s) placed by ruling, read by "
             "their stored side")
    echo("  not read here (a run's): its --since/--until range, its window and in-play read, the exchange's open "
         "list, the claims of a new market against a stored row's side (a stored row is never placed again)")
    present = {k[0] for legs in c["before"].values() for k in legs}
    for mid in c["match_ids"]:
        if mid not in c["games"]:
            echo(f"  match {mid}: not in this copy")
        elif mid not in present:
            echo(f"  match {mid} ({_game_text(c['games'][mid])}): no tickered Kalshi leg in this copy")
    counts = {"events": len(c["events"]), "events_with_legs": len(c["before"]),
              "events_pair_formed": sum(1 for ev in c["before"] if len(c["names"].get(ev, [])) == 2),
              "stored_legs": len(c["verdicts"]), "own_game": 0, "own_game_wrong_side": 0, "another_game": 0,
              "refused": 0,
              "not_formable": 0, "not_stored": 0, "split_events": 0}
    for ev in c["events"]:
        legs = c["before"].get(ev)
        if not legs:
            echo(f"\nEVENT {ev}: no stored leg in this copy")
            continue
        on = sorted({k[0] for k in legs})
        if len(on) > 1:
            counts["split_events"] += 1
        echo(f"\nEVENT {ev}" + (f" · SPLIT: its stored legs sit on {len(on)} games" if len(on) > 1 else ""))
        echo("  BEFORE (stored):")
        for (mid, sel, tic), caps in sorted(legs.items(), key=lambda x: (x[0][0], x[0][1], x[0][2])):
            echo(f"    {sel} {tic} on match {mid} ({_game_text(c['games'].get(mid))}) · {len(caps)} capture(s) "
                 f"{min(caps)[:19]} .. {max(caps)[:19]}")
        sib = c["sibs"].get(ev, [])
        echo("  AFTER (the matcher on the store):")
        if not sib:
            echo(f"    no settled row of this event: {NOT_FORMABLE}")
        else:
            nm = c["names"].get(ev, [])
            echo(f"    the store's names: {' / '.join(nm) if nm else 'none'}"
                 + ("" if len(nm) == 2 else f" ({len(nm)} name(s): the pair cannot be formed)"))
            for r in sorted(sib, key=lambda r: r["ticker"]):
                echo(f"    {r['ticker']} ({r['yes_sub_title'] or 'no name'}): "
                     f"{_after_text(c['after'][r['ticker']], c['games'])} · {_stored_text(r)}")
        echo("  VERDICT per stored leg:")
        for (mid, sel, tic) in sorted(legs, key=lambda k: (k[0], k[1], k[2])):
            kind, v = c["verdicts"][(mid, sel, tic)]
            echo(f"    {sel} {tic} on match {mid}: {v}")
            counts[kind] += 1
    if c["lines"]:
        echo("\nTHE MATCHER'S LINES (those naming an event read)")
        for ln in c["lines"]:
            echo(ln)
    echo("\nKALSHI-PAIR-RECEIPT " + json.dumps(counts, sort_keys=True))
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="#413 (addendum 230 item 0(a)): the shared matcher's pair, before and "
                                             "after, over the stored snapshots — read-only")
    ap.add_argument("--db", default=None, help="a .backup copy of the database outside the repo's data/, opened "
                                               "mode=ro&immutable=1 (required)")
    ap.add_argument("--match-ids", default=",".join(str(m) for m in DEFAULT_MATCH_IDS),
                    help="comma-separated match ids (machine-local; default: the laptop's ids of addendum 44 item "
                         "2's and addendum 37's receipts)")
    ap.add_argument("--events", default=",".join(DEFAULT_EVENTS),
                    help="comma-separated event tickers (the same on every machine; default: the nine KXNCAAFGAME "
                         "2026-10-10 events of addendum 37's receipt, the UGAALA split among them); '' for none")
    a = ap.parse_args(argv)
    from src.walters import mlb_pitchers_gate as mp
    try:
        match_ids, events = _ids(a.match_ids), _events(a.events)
        path = mp.check_db(a.db)
        for sc in SIDECARS:
            if path.with_name(path.name + sc).exists():
                raise mp.GateRefused(f"--db {a.db} has a {sc} sidecar ({path.name + sc}): not a fresh .backup copy; "
                                     "immutable=1 would ignore it and read a stale file; take a fresh .backup copy")
        mp.open_ro(path).close()
    except (mp.GateRefused, Refused) as err:
        print(f"REFUSED: {err}; nothing read")
        return REFUSED
    import sqlite3

    from sqlalchemy.exc import SQLAlchemyError
    db_text = f"--db {path} (a .backup copy, opened {mp.COPY_URI_QUERY.lstrip('?')})"
    lines: list[str] = []
    try:
        with mp.readonly_session(path) as s:
            report(collect(s, match_ids, events), db_text, echo=lines.append)
    except Refused as err:
        print(f"REFUSED: --db {path}: {err}; nothing read")
        return REFUSED
    except (SQLAlchemyError, sqlite3.Error) as err:     # a copy without the schema the read needs
        why = (str(err).strip().splitlines() or [""])[0]
        print(f"REFUSED: --db {path}: cannot be read as the schema the receipt needs ({type(err).__name__}: {why}); "
              "nothing read")
        return REFUSED
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
