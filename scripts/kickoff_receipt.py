"""
KICKOFF RECEIPT (ARCHITECT 2026-10-02, NCAA fixtures WKU@NMSU, UNT@Tulsa:
"Receipt: stored utc_date vs provider vs the in-play test's inputs; fix
whichever is wrong (stored kickoff +24h, or rollover logic)."). READ-ONLY.

For each match (by id, or by --find "<home substring>" on --date):
  1. STORED   matches row: utc_date, status, status_raw, external_ids.
  2. PROVIDER api-sports american-football /games?id=<source id>: the raw
              date block (date / time / timestamp / timezone) and the
              timestamp in UTC. One GET per match; --no-provider skips it.
  3. IN-PLAY  every export under --exports that carries the match: the
              file, exported_at, desk_meta.as_of, the row's utc_date, the
              Desk's venue reason, and the in-play test recomputed on the
              file's own inputs (utc_ms(row utc) <= as_of).

    python scripts/kickoff_receipt.py --find "New Mexico" --find "Tulsa" --date 2026-10-01
    python scripts/kickoff_receipt.py --id 123 --id 456 --no-provider
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def stored(ids: list[int], finds: list[str], day: str | None) -> list[dict]:
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Match, Team

    out = []
    with session_scope() as s:
        q = select(Match)
        if ids:
            q = q.where(Match.id.in_(ids))
        else:
            d = datetime.fromisoformat(day)
            q = q.where(Match.utc_date >= d - timedelta(days=1), Match.utc_date < d + timedelta(days=3))
        for m in s.execute(q.order_by(Match.utc_date)).scalars():
            home, away = s.get(Team, m.home_team_id), s.get(Team, m.away_team_id)
            names = f"{away.name if away else '?'} @ {home.name if home else '?'}"
            if finds and not any(f.lower() in names.lower() for f in finds):
                continue
            out.append({"id": m.id, "game": names, "utc_date": m.utc_date.isoformat(),
                        "status": getattr(m.status, "value", m.status), "status_raw": m.status_raw,
                        "external_ids": m.external_ids or {}})
        s.rollback()
    return out


def provider(source_id: str) -> dict:
    from src.adapters.api_american_football import APIAmericanFootballAdapter

    data = APIAmericanFootballAdapter()._get("games", {"id": source_id})
    resp = data.get("response") or []
    if not resp:
        return {"error": "no game returned"}
    game = resp[0].get("game") or resp[0]
    block = game.get("date") or {}
    ts = block.get("timestamp") if isinstance(block, dict) else None
    return {"date_block": block, "status": (game.get("status") or {}),
            "timestamp_utc": datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if ts else None}


def in_play(match_id: int, exports: str) -> list[dict]:
    from src.walters.desk_policy import utc_ms

    rows = []
    for path in sorted(glob.glob(os.path.join(exports, "**", "*.json"), recursive=True)):
        try:
            doc = json.load(open(path))
        except (OSError, ValueError):
            continue
        if not isinstance(doc, dict):
            continue
        for r in (doc.get("fixtures") or doc.get("predictions") or doc.get("rows") or []):
            if not isinstance(r, dict) or r.get("match_id") != match_id:
                continue
            as_of = (doc.get("desk_meta") or {}).get("as_of") or doc.get("exported_at")
            desk = r.get("desk") or {}
            reason = desk.get("reason") or (r.get("desk_venue") or {}).get("reason")
            u, a = utc_ms(r.get("utc_date")), utc_ms(as_of)
            rows.append({"file": os.path.relpath(path, exports), "exported_at": doc.get("exported_at"),
                         "as_of": as_of, "row_utc_date": r.get("utc_date"), "status": r.get("status"),
                         "reason": reason, "in_play_recomputed": (u <= a) if u == u and a == a else None})
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--id", type=int, action="append", default=[])
    ap.add_argument("--find", action="append", default=[], help="team-name substring (home or away)")
    ap.add_argument("--date", help="YYYY-MM-DD, the day to search around (with --find)")
    ap.add_argument("--exports", default="exports")
    ap.add_argument("--no-provider", action="store_true")
    a = ap.parse_args(argv)
    if not a.id and not (a.find and a.date):
        ap.error("give --id, or --find with --date")
    games = stored(a.id, a.find, a.date)
    print(f"KICKOFF RECEIPT · {len(games)} match(es)")
    for g in games:
        print(f"\n== {g['id']} {g['game']}")
        print(f"  STORED    utc_date {g['utc_date']} · status {g['status']} ({g['status_raw']}) · ext {g['external_ids']}")
        sid = g["external_ids"].get("api_american_football")
        if a.no_provider or not sid:
            print("  PROVIDER  skipped" + ("" if sid else " (no api_american_football id)"))
        else:
            try:
                p = provider(sid)
                print(f"  PROVIDER  timestamp -> {p.get('timestamp_utc')} · date block {json.dumps(p.get('date_block'))}"
                      f" · status {json.dumps(p.get('status'))}" if "error" not in p else f"  PROVIDER  {p['error']}")
            except Exception as e:  # noqa: BLE001 — a receipt reports, never crashes
                print(f"  PROVIDER  error: {e}")
        rows = in_play(g["id"], a.exports)
        if not rows:
            print(f"  IN-PLAY   no export under {a.exports}/ carries this match")
        for r in rows:
            print(f"  IN-PLAY   {r['file']} · as_of {r['as_of']} · row utc {r['row_utc_date']} · "
                  f"recomputed in-play {r['in_play_recomputed']} · reason {r['reason']!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
