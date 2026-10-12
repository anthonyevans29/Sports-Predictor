"""
THE MATCHER'S READ-ONLY REPLAY (ARCHITECT 2026-10-12, addendum 50 item 6(b)), verbatim:

"The switch is a PR of its own. First, and by itself, main takes the new module, its tests and a read-only replay; the
two sync paths stay as they are. The replay fetches each series' open markets once, places them with the new module on
the stored games, opened read-only, and stores nothing. For each series it prints what the new module places and what
it refuses, by reason, beside the legs main's matcher stored at its last sync, and then every leg that differs: on
another game or side, stored by main and refused now, placed now and not stored by main. The operator runs it in the
morning block, straight after the day's Kalshi syncs. The switch PR carries that console, and I call it on that."
- Every series the syncs read: MLB, NFL, NHL, NCAA, and each soccer series the day resolves.
- The replay keeps the markets it fetched in a file under logs/, so that a test can hold a real payload. It is public
  market data. The operator sends it to me.

How it reads, so the console can be checked against it:
- The stored games: the series' own competition (the one map, venue.KALSHI_SERIES_BY_COMPETITION, read by
  kalshi_sync.series_competition; a soccer series by the competition it is resolved for), loaded as the syncs load
  them (kalshi_sync.stored_games: every row whose kickoff falls in the span of the events' days), through a mode=ro
  session (venue_quote_age.readonly_session): nothing is written to the database.
- The window each sync uses by default: the shared path now-1d..now+2d, the soccer path now-1d..now+7d with its 0.10
  spread guard and its Tie legs. `now` is the moment that series' markets were fetched (each series is stamped after
  its own fetch, as a sync stamps its run: #470 item 3).
- "The legs main's matcher stored at its last sync": the kalshi snapshots of the competition's games written at the
  newest capture time at or before that fetch (one sync run writes every leg with one captured_at; a sync after the
  fetch is not read: #470 item 2), each with its stored market ticker. Legs are compared by ticker; a stored leg with
  no ticker (before the ticker column) is counted, not compared.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOCCER_MAX_SPREAD = 0.10        # the soccer sync's default guard (UNL's frozen value too)
STALE_MAIN_H = 3.0              # main's newest stored legs older than this are flagged (the replay runs after syncs)


def shared_series() -> dict:
    """{series: competition} of the two-way series the shared path reads: the one map
    (venue.KALSHI_SERIES_BY_COMPETITION) less the soccer competitions (addendum 51 item 7)."""
    from src.adapters.kalshi import KalshiAdapter
    from src.walters.venue import KALSHI_SERIES_BY_COMPETITION
    return {s: c for c, s in KALSHI_SERIES_BY_COMPETITION.items() if c not in KalshiAdapter.SOCCER_GAME_SERIES}


def series_plan(adapter, only: list[str] | None = None) -> list[dict]:
    """[{series, competition, path}] for every series the syncs read: the two-way series, then each soccer
    competition whose series resolves (mapped or discovered, as sync-kalshi-soccer resolves it)."""
    out = [{"series": s, "competition": c, "path": "shared"} for s, c in shared_series().items()]
    # the mapped competitions and the discoverable ones, as sync-kalshi-soccer resolves them (Codex on #461); a code
    # whose series does not resolve is listed with why, never silently left out
    codes = list(adapter.SOCCER_GAME_SERIES) + [c for c in getattr(adapter, "SOCCER_SERIES_DISCOVERY", {})
                                                 if c not in adapter.SOCCER_GAME_SERIES]
    for code in codes:
        series, how = adapter.resolve_soccer_series(code, None)
        if series:
            out.append({"series": series, "competition": code, "path": "soccer", "how": how})
        else:
            out.append({"series": f"(unresolved {code})", "competition": code, "path": "soccer", "unresolved": how})
    if only:
        want = {x.upper() for x in only}
        out = [p for p in out if p["series"].upper() in want or p["competition"].upper() in want]
    return out


def fetch(only: list[str] | None = None, progress=print) -> dict:
    """Fetch each series' open markets once and keep them under logs/ (public market data). Returns the payload."""
    from src.adapters.kalshi import KalshiAdapter
    from src.timeutil import utc_now_naive

    adapter = KalshiAdapter()
    now = utc_now_naive().replace(microsecond=0)
    payload = {"kind": "kalshi_replay_markets", "fetched_at": now.isoformat(), "series": {}}
    for p in series_plan(adapter, only):
        if p.get("unresolved"):
            payload["series"][p["series"]] = {**p, "markets": [], "error": f"series not resolved: {p['unresolved']}"}
            progress(f"  {p['competition']}: series not resolved ({p['unresolved']})")
            continue
        try:
            mks = adapter.open_markets_for_series(p["series"])
            # each series stamped after its own fetch, as a sync stamps its run (#470 item 3), to the microsecond as
            # a sync stores captured_at: a capture made earlier in the same second is before the fetch (Codex on #475)
            payload["series"][p["series"]] = {**p, "markets": mks, "fetched_at": utc_now_naive().isoformat()}
        except Exception as e:  # noqa: BLE001 - one series' failure is printed; the others replay
            payload["series"][p["series"]] = {**p, "markets": [], "error": f"{type(e).__name__}: {e}"[:200]}
        progress(f"  fetched {p['series']} ({p['competition']}): "
                 + (payload["series"][p["series"]].get("error") or f"{len(payload['series'][p['series']]['markets'])} "
                    "open markets"))
    logs = REPO / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / f"kalshi_replay_{now:%Y%m%dT%H%M%SZ}.json"
    path.write_text(json.dumps(payload, indent=1, default=str))
    payload["kept_at"] = str(path.relative_to(REPO))
    return payload


def _main_legs(s, comp_id: int, market: str, before: datetime | None = None) -> dict:
    """The legs main's matcher stored at its last sync at or before `before` (the series' fetch: #470 item 2):
    {ticker: (match_id, selection)}, with the capture time and the count of untickered legs."""
    from sqlalchemy import func, select, text

    from src.db.schema import Match, OddsSnapshot

    base = (select(OddsSnapshot).join(Match, Match.id == OddsSnapshot.match_id)
            .where(Match.competition_id == comp_id, OddsSnapshot.source == "kalshi", OddsSnapshot.market == market))
    # the newest capture time, compared inside SQL (the stored text is matched as stored)
    newest = (select(func.max(OddsSnapshot.captured_at)).join(Match, Match.id == OddsSnapshot.match_id)
              .where(Match.competition_id == comp_id, OddsSnapshot.source == "kalshi", OddsSnapshot.market == market,
                     *([OddsSnapshot.captured_at <= before] if before is not None else []))
              .scalar_subquery())
    rows = list(s.execute(base.where(OddsSnapshot.captured_at == newest)).scalars())
    if not rows:
        return {"at": None, "legs": {}, "untickered": 0}
    last = rows[0].captured_at
    cols = {r[1] for r in s.execute(text("PRAGMA table_info(odds_snapshots)"))}
    tick = {}
    if "market_ticker" in cols and rows:
        ids = ",".join(str(r.id) for r in rows)
        tick = {i: t for i, t in s.execute(text(f"SELECT id, market_ticker FROM odds_snapshots WHERE id IN ({ids})"))
                if t}
    legs, untickered = {}, 0
    for r in rows:
        t = tick.get(r.id)
        if t:
            legs[t] = (r.match_id, r.selection)
        else:
            untickered += 1
    return {"at": last, "legs": legs, "untickered": untickered}


def replay(payload: dict, progress=print) -> dict:
    """Place every kept series' markets with the new module on the stored games (read-only) and compare with main's
    last sync. Stores nothing. Returns per-series results; prints the console."""
    from sqlalchemy import select

    from src.adapters.kalshi import KalshiAdapter
    from src.db.schema import Competition, Match
    from src.ingestion import kalshi_match as km
    from src.ingestion.kalshi_sync import stored_games
    from src.walters.venue_quote_age import readonly_session

    out = {}
    with readonly_session() as s:
        for series, p in payload["series"].items():
            mks = p.get("markets") or []
            soccer = p.get("path") == "soccer"
            head = f"== {series} ({p['competition']}, {'soccer' if soccer else 'shared'} path)"
            if p.get("error"):
                progress(f"{head} · fetch failed: {p['error']}")
                out[series] = {"error": p["error"]}
                continue
            comp = s.execute(select(Competition).where(Competition.code == p["competition"])).scalar_one_or_none()
            if comp is None:
                progress(f"{head} · competition {p['competition']} not in the DB")
                out[series] = {"error": "competition not in DB"}
                continue
            # the series' own fetch time (#470 item 3); a file kept before it was stamped per series has the run's
            now = datetime.fromisoformat(p.get("fetched_at") or payload["fetched_at"])
            games = stored_games(s, [comp.id], mks)
            lo, hi = now - timedelta(days=1), now + timedelta(days=7 if soccer else 2)
            res = km.place(mks, games, now=now, lo=lo, hi=hi, implied_prob=KalshiAdapter.implied_prob,
                           is_tie=KalshiAdapter.is_tie_market if soccer else None,
                           spread=KalshiAdapter.spread_dollars if soccer else None,
                           max_spread=SOCCER_MAX_SPREAD if soccer else None)
            main = _main_legs(s, comp.id, "1X2" if soccer else "ML", before=now)
            new = {mk.get("ticker"): key for key, mk in res.placed.items()}
            names = {g.id: f"{g.away_team.name} @ {g.home_team.name}" for g in games if g.home_team and g.away_team}

            def game(mid):
                if mid not in names:
                    m = s.get(Match, mid)
                    names[mid] = f"{m.away_team.name} @ {m.home_team.name}" if m and m.home_team and m.away_team \
                        else "?"
                return f"{mid} {names[mid]}"
            differ = []
            for t in sorted(set(main["legs"]) | set(new), key=str):
                a, b = main["legs"].get(t), new.get(t)
                if a and b and a != b:
                    differ.append(f"  ✗ {t}: on another game or side · main {game(a[0])} {a[1]} · new {game(b[0])} "
                                  f"{b[1]}")
                elif a and not b:
                    differ.append(f"  ✗ {t}: stored by main and refused now · main {game(a[0])} {a[1]} · new: "
                                  f"{res.why.get(t) or 'not in the open markets now'}")
                elif b and not a:
                    differ.append(f"  ✗ {t}: placed now and not stored by main · new {game(b[0])} {b[1]}")
            progress(f"{head} · {len(mks)} open markets · {len(games)} stored games on the events' days")
            progress(f"  new: placed {len(res.placed)} · refused {sum(res.refused.values())}")
            for ln in km.console_lines(res):
                progress(ln)
            # The newest legs main stored, by capture time. A sync that stored nothing leaves no row, so these can be
            # an older run's: the age is printed and an old capture flagged, never presented as this morning's (Codex
            # on #461)
            age_h = (now - main["at"]).total_seconds() / 3600 if main["at"] else None
            progress("  main's newest stored legs: "
                     + (f"captured {main['at'].isoformat()} ({age_h:.1f}h before these markets were fetched)"
                        if main["at"] else "— (no kalshi legs stored)")
                     + f": {len(main['legs'])} tickered legs"
                     + (f" · {main['untickered']} without a ticker (counted, not compared)" if main["untickered"] else ""))
            if age_h is not None and age_h > STALE_MAIN_H:
                progress(f"  ⚠ main's newest legs are {age_h:.1f}h old: a later sync stored none, or did not run. "
                         "The differences below are against that older capture.")
            progress(f"  legs that differ: {len(differ)}")
            for ln in differ:
                progress(ln)
            out[series] = {"placed": len(res.placed), "refused": dict(res.refused), "main_legs": len(main["legs"]),
                           "main_age_h": age_h,
                           "main_at": main["at"], "untickered": main["untickered"], "differ": differ,
                           "games": len(games)}
    return out
