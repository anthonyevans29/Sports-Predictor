"""refresh-by-id: every stored SCHEDULED game of a competition kicking off in the next N days, refreshed
from the provider by the game's OWN id (ARCHITECT 2026-10-09, addendum 21 item 1).

RULED: "For NCAA, the kickoff, status and score of every stored SCHEDULED game kicking off in the next
seven days are refreshed from the provider by the game's own id, at least once a day on the host and in
the laptop's morning chain. The listing reads stay: they find games we do not hold. A game the provider
does not return by id is never guessed and never deleted: it is counted and listed, and nothing else is
done to it."

Why by id: the provider's listing (season or by-date) no longer carries college games that have not
started, while the games still answer by id (addendum 21 receipts: 96 of 97 SCHEDULED rows in the next
72h carried an id not in the season listing; /games?id=23653 resolves Georgia at Alabama 23:30Z).

- Selection: stored rows of the competition, status SCHEDULED, with a stored kickoff on the UTC dates
  today .. today+days (the same dates the ncaa-schedule chain's listing reads cover). A row with no
  provider id is counted and listed, never looked up by anything else.
- One GET per game: `adapter.get_game(id)` (GET /games?id=, src/adapters/api_american_football.py).
- Rate limit, the sync-odds-football rule (src/ingestion/service.py sync_odds_nfl): calls PACED below the
  provider's limit (SP_ODDS_FOOTBALL_RPM, default 280/min); a game whose answer is still 429 after the
  adapter's in-call retry (RateLimited) is DEFERRED and retried after the window (Retry-After, else 60s),
  up to ODDS_RETRY_ROUNDS rounds; never dropped. One still rate limited after the last round is listed.
- Applied from the answer: kickoff (utc_date), status (the adapter's _STATUS map: an unknown code stays
  SCHEDULED, law 4) and the score (only when the provider gives one: a present score is never blanked).
- Never guessed: no answer (an empty response) = NOT FOUND, counted and listed, the row untouched. An
  answer for different teams than the stored row = REFUSED, listed, the row untouched. A lookup error =
  UNRESOLVED (never read as absent), listed, the row untouched.

NAMED GAMES (ARCHITECT 2026-10-09, addendum 23 A1, the closing run's schedule read for NFL): "NFL's schedule read
is by id: refresh-by-id (#378) for the covered games, and a covered game that is not found, refused, unresolved or
still rate limited fails the run at that step." `match_ids` selects exactly those stored rows of the competition
(any status, any date; the window is not applied), and `named_failures` lists every named game the answer did not
refresh: not found, refused, excluded, no provider id, unresolved, still rate limited, or not stored in the
competition at all. The CLI's --match-ids exits 1 on any of them. Without match_ids nothing changes.
"""
from __future__ import annotations

import os
from datetime import datetime, time, timedelta

SOURCE = "api_american_football"


def _iso(dt):
    return dt.isoformat(sep=" ", timespec="minutes") if dt is not None else None


def window(today, days: int) -> tuple[datetime, datetime]:
    """[today 00:00Z, today+days+1 00:00Z): the UTC dates today .. today+days."""
    lo = datetime.combine(today, time())
    return lo, lo + timedelta(days=days + 1)


def refresh(competition_code: str, adapter, days: int = 7, now=None, progress=None,
            source: str = SOURCE, match_ids: set[int] | None = None) -> dict:
    """Refresh the competition's stored SCHEDULED games in the window by id. Returns the receipt."""
    from sqlalchemy import select

    from src.adapters.api_american_football import RateLimited
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus
    from src.ingestion import service as svc
    from src.timeutil import utc_now_naive

    def report(msg):
        if progress:
            progress(msg)

    now = now or utc_now_naive()
    lo, hi = window(now.date(), days)
    rpm = max(1, int(os.environ.get("SP_ODDS_FOOTBALL_RPM") or 280))
    gap, last = 60.0 / rpm, [None]
    requests = [0]

    def paced(sid):               # the sync-odds-football pacing, verbatim in shape
        if last[0] is not None:
            wait = gap - (svc._odds_clock() - last[0])
            if wait > 0:
                svc._odds_sleep(wait)
        last[0] = svc._odds_clock()
        requests[0] += 1
        return adapter.get_game(str(sid), competition_code)

    r = {"kind": "refresh_by_id", "competition": competition_code, "source": source, "days": days,
         "now": _iso(now), "window": [_iso(lo), _iso(hi)], "selected": 0, "asked": 0, "requests": 0,
         "unchanged": 0, "updated": 0, "kickoff_moved": [], "status_changed": [], "score_changed": [],
         "not_found": [], "refused": [], "excluded": [], "no_id": [], "unresolved": [],
         "rate_limited": 0, "recovered": 0, "still_rate_limited": []}
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == competition_code)).scalar_one_or_none()
        if comp is None:
            r["error"] = f"competition {competition_code} not in the DB (run sync-competitions first)"
            return r
        if match_ids is None:
            rows = list(s.execute(select(Match).where(
                Match.competition_id == comp.id,
                Match.status == MatchStatus.SCHEDULED,
                Match.utc_date >= lo, Match.utc_date < hi,
            ).order_by(Match.utc_date, Match.id)).scalars())
        else:                     # A1 (addendum 23): exactly the named games of this competition, by stored id
            rows = list(s.execute(select(Match).where(
                Match.competition_id == comp.id, Match.id.in_(sorted(match_ids)),
            ).order_by(Match.utc_date, Match.id)).scalars())
            r["named"] = sorted(match_ids)
            r["not_selected"] = sorted(set(match_ids) - {m.id for m in rows})
        r["selected"] = len(rows)

        def game(m):
            return f"{m.away_team.name if m.away_team else '?'} @ {m.home_team.name if m.home_team else '?'}"

        def line(m, sid, **extra):
            return {"match_id": m.id, "id": str(sid) if sid is not None else None, "game": game(m),
                    "stored_kickoff": _iso(m.utc_date), **extra}

        queue = []
        for m in rows:
            sid = (m.external_ids or {}).get(source)
            if not sid:
                r["no_id"].append(line(m, None))
                continue
            queue.append((m, sid))
        r["asked"] = len(queue)
        if match_ids is None:
            report(f"  {competition_code} refresh by id: {len(rows)} stored SCHEDULED game(s) on {lo:%Y-%m-%d} .. "
                   f"{(hi - timedelta(days=1)):%Y-%m-%d} (UTC) · asking {len(queue)} by id · paced at {rpm}/min")
        else:
            report(f"  {competition_code} refresh by id: {len(match_ids)} named game(s), {len(rows)} stored · "
                   f"asking {len(queue)} by id · paced at {rpm}/min")

        answers, rnd = [], 0
        while queue:
            deferred, wait = [], 0.0
            for m, sid in queue:
                try:
                    answers.append((m, sid, paced(sid), rnd))
                except RateLimited as e:       # deferred, never dropped (the sync-odds-football rule)
                    deferred.append((m, sid))
                    wait = max(wait, e.retry_after)
                except Exception as e:  # noqa: BLE001 — UNRESOLVED, never read as absent; row untouched
                    r["unresolved"].append(line(m, sid, error=f"{type(e).__name__}: {str(e)[:160]}"))
            if not deferred:
                break
            if rnd == 0:
                r["rate_limited"] = len(deferred)
            if rnd >= svc.ODDS_RETRY_ROUNDS:
                r["still_rate_limited"] = [line(m, sid) for m, sid in deferred]
                report(f"    ✗ still rate limited after {rnd} retry round(s): {len(deferred)} game(s) not refreshed")
                break
            rnd += 1
            report(f"    ↻ {len(deferred)} game(s) rate limited — retrying after {wait:.0f}s (round {rnd})")
            svc._odds_sleep(wait)
            last[0] = None
            queue = deferred
        r["recovered"] = sum(1 for *_, k in answers if k > 0)
        r["requests"] = requests[0]

        for m, sid, (exists, nm), _ in answers:
            if not exists:
                r["not_found"].append(line(m, sid))     # never guessed, never deleted: listed, nothing else
                continue
            if nm is None:
                r["excluded"].append(line(m, sid, why="the provider's game is non-competitive (filtered)"))
                continue
            def tsid(t):
                v = (t.external_ids or {}).get(source) if t is not None else None
                return str(v) if v is not None else None
            hs, as_ = tsid(m.home_team), tsid(m.away_team)
            if (str(nm.home_team_source_id), str(nm.away_team_source_id)) != (hs, as_):
                r["refused"].append(line(m, sid, why=f"the answer's teams {nm.home_team_source_id}/"
                                                     f"{nm.away_team_source_id} are not the stored row's {hs}/{as_}"))
                continue
            changed = False
            if nm.utc_date is not None and nm.utc_date != m.utc_date:
                r["kickoff_moved"].append(line(m, sid, provider_kickoff=_iso(nm.utc_date)))
                m.utc_date = nm.utc_date
                changed = True
            if nm.status is not None and nm.status != m.status:
                r["status_changed"].append(line(m, sid, stored_status=m.status.value, provider_status=nm.status.value))
                m.status = nm.status
                changed = True
            new_h = nm.home_score if nm.home_score is not None else m.home_score
            new_a = nm.away_score if nm.away_score is not None else m.away_score
            if (new_h, new_a) != (m.home_score, m.away_score):
                r["score_changed"].append(line(m, sid, stored_score=[m.home_score, m.away_score],
                                               provider_score=[new_h, new_a]))
                m.home_score, m.away_score = new_h, new_a
                changed = True
            if nm.status_raw:
                m.status_raw = nm.status_raw
            r["updated" if changed else "unchanged"] += 1
    return r


NAMED_FAILURE_KEYS = ("not_found", "refused", "excluded", "no_id", "unresolved", "still_rate_limited")


def named_failures(r: dict) -> list[str]:
    """A1 (addendum 23): every named game the answer did not refresh, one line each (empty without match_ids)."""
    if "named" not in r:
        return []
    out = [f"match {mid}: not stored in {r['competition']}" for mid in r.get("not_selected") or []]
    for key in NAMED_FAILURE_KEYS:
        out += [f"match {x['match_id']} id {x['id']} {x['game']}: {key.replace('_', ' ')}" for x in r[key]]
    return out


def format_lines(r: dict) -> list[str]:
    """The printed receipt: counts first, then every listed game (both times where a kickoff moved)."""
    if r.get("error"):
        return [f"REFRESH-BY-ID {r['competition']}: REFUSED — {r['error']}"]
    out = [f"REFRESH-BY-ID {r['competition']} ({r['source']}) window {r['window'][0]} .. {r['window'][1]} UTC · "
           f"selected {r['selected']} · asked {r['asked']} · unchanged {r['unchanged']} · updated {r['updated']} "
           f"(kickoff moved {len(r['kickoff_moved'])}, status {len(r['status_changed'])}, "
           f"score {len(r['score_changed'])}) · not found {len(r['not_found'])} · refused {len(r['refused'])} · "
           f"no id {len(r['no_id'])} · unresolved {len(r['unresolved'])} · rate limited {r['rate_limited']} "
           f"(recovered {r['recovered']}, still {len(r['still_rate_limited'])}) · requests {r['requests']}"]
    for x in r["kickoff_moved"]:
        out.append(f"  kickoff moved: match {x['match_id']} id {x['id']} {x['game']}: "
                   f"{x['stored_kickoff']} -> {x['provider_kickoff']}")
    for x in r["status_changed"]:
        out.append(f"  status: match {x['match_id']} id {x['id']} {x['game']}: "
                   f"{x['stored_status']} -> {x['provider_status']}")
    for x in r["score_changed"]:
        out.append(f"  score: match {x['match_id']} id {x['id']} {x['game']}: "
                   f"{x['stored_score']} -> {x['provider_score']}")
    for key, label in (("not_found", "NOT FOUND by id (untouched)"), ("refused", "REFUSED (untouched)"),
                       ("excluded", "excluded (untouched)"), ("no_id", "no provider id (untouched)"),
                       ("unresolved", "UNRESOLVED (untouched)"),
                       ("still_rate_limited", "STILL RATE LIMITED (untouched)")):
        for x in r[key]:
            why = x.get("why") or x.get("error") or ""
            out.append(f"  {label}: match {x['match_id']} id {x['id']} {x['game']} "
                       f"stored {x['stored_kickoff']}" + (f" — {why}" if why else ""))
    for mid in r.get("not_selected") or []:
        out.append(f"  NAMED, NOT STORED in {r['competition']}: match {mid}")
    return out
