"""
NCAA PREGAME METADATA RECEIPT (ARCHITECT 2026-10-23, addendum 158 item 1(c)) — read-only, counts only.

Verbatim: "(c) With (b): a read-only pregame metadata receipt for the 2026 fixtures — orientation and neutral status
as known BEFORE kickoff (the CFBD labels are post-game; D8 needs pregame neutral), their observation times, and the
Kalshi benchmark's coverage (D11). Counts only."

What is known before kickoff, by source (each read as stored; nothing fetched):
  - OUR LISTING (the provider's matches row): home and away as listed. Its post-game check is the label's
    orientation (same = CFBD's home is our home; swapped = the reverse).
  - THE SAVED CFBD PAYLOADS (ncaa-cfbd-labels saves every /games response under exports/cfbd/, named
    cfbd_games_<year>_<UTC stamp>.json; the stamp is the observation time). A payload fetched before a game's kickoff
    lists it with CFBD's home, away and neutralSite as known then. A labelled game is found in it by its CFBD game id
    (the label's source_game_id), so no name is matched. The LATEST payload before kickoff is the pregame observation.
    Field names are discovered from each file (ncaa_cfbd.discover, law 1).
  - KALSHI (D11): a KXNCAAFGAME quote stored before kickoff (odds_snapshots, source "kalshi"), and a settled-market row
    (kalshi_settled_markets, where that table exists), per game.

The population is the stored NCAA games of the season carrying a CURRENT CFBD label (L3), by season_type, and the
season's stored fixtures not yet labelled (counted; no pregame observation is joined to them by name). Counts only: no
score, no result, no rate (the 2026 fence, addendum 86 item 3 Q2, holds).
"""
from __future__ import annotations

import contextlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

RULING = "ARCHITECT 2026-10-23, addendum 158 item 1(c)"
STAMP = re.compile(r"^cfbd_games_(\d{4})_(\d{8}T\d{6}Z)\.json$")
LEADS = ((24, "< 24h"), (72, "1-3 days"), (168, "3-7 days"), (None, "> 7 days"))     # hours before kickoff


def payload_stamp(path: Path) -> tuple[int, datetime] | None:
    m = STAMP.match(path.name)
    if not m:
        return None
    return int(m.group(1)), datetime.strptime(m.group(2), "%Y%m%dT%H%M%SZ")


def load_payloads(payload_dir: str | Path, year: int) -> tuple[list[tuple[datetime, dict]], list[str]]:
    """[(stamp, {cfbd id: {home, away, neutral}})] for the year's saved payloads in stamp order, and every file read
    but not used (with why). Read-only."""
    from src.ingestion.ncaa_cfbd import discover

    out, skipped = [], []
    d = Path(payload_dir)
    for f in sorted(d.glob(f"cfbd_games_{year}_*.json")) if d.is_dir() else []:
        st = payload_stamp(f)
        if st is None or st[0] != year:
            skipped.append(f"{f.name}: name carries no stamp")
            continue
        try:
            recs = json.loads(f.read_text())
        except (OSError, ValueError) as e:
            skipped.append(f"{f.name}: unreadable ({type(e).__name__})")
            continue
        if not isinstance(recs, list) or not recs:
            skipped.append(f"{f.name}: no records")
            continue
        keys, missing = discover(recs[0])
        if missing or not keys.get("id"):
            skipped.append(f"{f.name}: fields not found ({', '.join(missing + ([] if keys.get('id') else ['id']))})")
            continue
        games = {}
        for r in recs:
            gid = r.get(keys["id"])
            if isinstance(gid, int):
                nv = r.get(keys["neutral"])
                games[gid] = {"home": r.get(keys["home"]), "away": r.get(keys["away"]),
                              "neutral": None if nv is None else bool(nv)}
        out.append((st[1], games))
    out.sort(key=lambda x: x[0])
    return out, skipped


def _lead(hours: float) -> str:
    for cap, name in LEADS:
        if cap is None or hours < cap:
            return name
    return LEADS[-1][1]


@contextlib.contextmanager
def readonly_session(path: Path):
    """The DB opened with a mode=ro URI (Codex on #698): no connect hook, no PRAGMA, no commit; a missing file is
    refused, never created (venue_quote_age.readonly_session's open, on a named path)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    path = Path(path)
    if not path.is_file():
        raise SystemExit(f"no database at {path}: the receipt never creates one")
    eng = create_engine(f"sqlite:///file:{path.as_posix()}?mode=ro&uri=true",
                        connect_args={"uri": True, "check_same_thread": False})
    s = Session(eng)
    try:
        yield s
    finally:
        s.rollback()
        s.close()
        eng.dispose()


FLIP = {"same": "swapped", "swapped": "same"}


def pregame_orientation(payload_home, lab) -> str:
    """Our listing against CFBD's home AS KNOWN BEFORE KICKOFF (Codex on #698): the label's post-game orientation when
    the payload's home is the label's source home, its reverse when it is the label's source away, else unknown."""
    o = getattr(lab, "orientation", None)
    if payload_home is None or o not in FLIP:
        return "unknown"
    if payload_home == lab.source_home_team:
        return o
    if payload_home == getattr(lab, "source_away_team", None):
        return FLIP[o]
    return "unknown"


def receipt(season: str = "2026", payload_dir: str | Path = "exports/cfbd", now: datetime | None = None,
            db_path: str | Path | None = None) -> dict:
    """The receipt (module docstring). One mode=ro session (readonly_session); nothing written. `db_path`: the SQLite
    file (default: the configured DATABASE_URL's)."""
    from sqlalchemy import func, inspect, select

    from src.db.schema import Competition, Match, MatchStatus, NCAACFBDLabel, OddsSnapshot, Sport
    from src.ingestion import kalshi_history
    from src.ingestion.ncaa_cfbd import label_load_options, latest_record_stamps
    from src.timeutil import utc_now_naive

    now = now or utc_now_naive()
    payloads, skipped = load_payloads(payload_dir, int(season))
    stamps = [p[0] for p in payloads]
    c: Counter = Counter()
    by_type: dict = {}
    if db_path is None:
        from src.walters.venue_quote_age import db_file_path
        db_path = db_file_path()
        if db_path is None:
            raise SystemExit("not a SQLite DATABASE_URL: the receipt is SQLite-only")
    with readonly_session(db_path) as s:
        insp = inspect(s.connection())
        has_labels = insp.has_table(NCAACFBDLabel.__tablename__)
        # migrated, not merely present (Codex on #698): an init_db()-created table without its migration's marker is
        # not a D11 source (kalshi_history.migrated)
        has_settled = kalshi_history.migrated(s)
        current = latest_record_stamps(s, [season]).get(season) if has_labels else None
        ncaa = (select(Match).join(Competition, Match.competition_id == Competition.id)
                .where(Match.sport == Sport.NFL, Competition.code == "NCAA", Match.season == season))
        matches = {m.id: m for m in s.execute(ncaa).scalars()}
        labels = {}
        if has_labels and current is not None and matches:
            labels = {lab.match_id: lab for lab in s.execute(
                select(NCAACFBDLabel).options(*label_load_options(s))
                .where(NCAACFBDLabel.season == season, NCAACFBDLabel.fetched_at == current,
                       NCAACFBDLabel.match_id.in_(list(matches)))).scalars()}
        kalshi_pre = set()
        if matches:
            for mid, at in s.execute(select(OddsSnapshot.match_id, func.min(OddsSnapshot.captured_at))
                                     .where(OddsSnapshot.match_id.in_(list(matches)), OddsSnapshot.source == "kalshi")
                                     .group_by(OddsSnapshot.match_id)).all():
                if at is not None and at < matches[mid].utc_date:
                    kalshi_pre.add(mid)
        settled = set()
        if has_settled and matches:
            from sqlalchemy import text
            settled = {r[0] for r in s.execute(text("SELECT DISTINCT match_id FROM kalshi_settled_markets WHERE "
                                                    "match_id IS NOT NULL AND series = 'KXNCAAFGAME'")).all()} & set(matches)
        for mid, m in sorted(matches.items(), key=lambda kv: (kv[1].utc_date, kv[0])):
            lab = labels.get(mid)
            if lab is None:
                if m.status in (MatchStatus.CANCELLED, MatchStatus.STALE_ORPHAN):
                    c["unlabelled_cancelled_or_orphan"] += 1
                elif m.utc_date >= now:
                    c["upcoming"] += 1
                    c["upcoming_kalshi_quote"] += mid in kalshi_pre
                else:
                    c["past_unlabelled"] += 1
                continue
            st = getattr(lab, "season_type", None) if "season_type" in lab.__dict__ else None
            t = by_type.setdefault(st or "(no season_type)", Counter())
            t["games"] += 1
            t[f"listing_{lab.orientation}"] += 1                       # our listing vs CFBD's post-game home
            t["kalshi_quote_before_kickoff"] += mid in kalshi_pre
            t["kalshi_settled_row"] += mid in settled
            pre = None
            if lab.source_game_id is not None:
                for at, games in reversed([p for p in payloads if p[0] < m.utc_date]):
                    if lab.source_game_id in games:
                        pre = (at, games[lab.source_game_id])
                        break
            if pre is None:
                t["no_pregame_payload"] += 1
                continue
            at, g = pre
            t["pregame_observed"] += 1
            t[f"lead {_lead((m.utc_date - at).total_seconds() / 3600)}"] += 1
            if g["neutral"] is None:
                t["neutral pregame unknown"] += 1
            elif lab.neutral is None:
                t["neutral post-game unknown"] += 1
            elif g["neutral"] == lab.neutral:
                t["neutral agrees" + (" (neutral)" if lab.neutral else "")] += 1
            else:
                t["neutral differs: pregame " + ("neutral" if g["neutral"] else "home") + ", post-game "
                  + ("neutral" if lab.neutral else "home")] += 1
            t["cfbd home unchanged" if g["home"] == lab.source_home_team else "cfbd home changed"] += 1
            t[f"pregame_listing_{pregame_orientation(g['home'], lab)}"] += 1     # as known before kickoff
        s.rollback()
    return {"season": season, "now": now, "payloads": len(payloads), "first": stamps[0] if stamps else None,
            "last": stamps[-1] if stamps else None, "skipped_files": skipped, "current_record": current,
            "by_type": by_type, "counts": c, "has_settled_table": has_settled, "stored": len(matches)}


def lines(r: dict) -> list[str]:
    L = [f"NCAA PREGAME METADATA RECEIPT ({RULING}) · read-only, counts only · season {r['season']} · now "
         f"{r['now']:%Y-%m-%d %H:%M}Z · stored NCAA games {r['stored']} · current label record "
         f"{r['current_record'] or 'none (no current label: nothing below is labelled)'}",
         f"  saved CFBD {r['season']} payloads read {r['payloads']}"
         + (f" (first {r['first']:%Y-%m-%d %H:%M}Z, last {r['last']:%Y-%m-%d %H:%M}Z)" if r["payloads"] else "")
         + (f" · files not used {len(r['skipped_files'])}" if r["skipped_files"] else "")]
    L += [f"    not used: {x}" for x in r["skipped_files"]]
    for st, t in sorted(r["by_type"].items()):
        rest = {k: v for k, v in t.items() if k not in ("games",)}
        L.append(f"  {st}: labelled {t['games']} · " + " · ".join(f"{k} {v}" for k, v in sorted(rest.items())))
    c = r["counts"]
    L.append(f"  not labelled: upcoming {c['upcoming']} (a Kalshi quote stored {c['upcoming_kalshi_quote']}) · past "
             f"without a current label {c['past_unlabelled']} · cancelled / orphan {c['unlabelled_cancelled_or_orphan']}")
    if not r["has_settled_table"]:
        L.append("  kalshi_settled_markets: not migrated here (migrate_kalshi_settled_markets.py's table and marker; "
                 "D11's read waits on its migration and its first NCAA pull)")
    L.append("  sources: listing = our matches row (home / away as the provider listed it): listing_* against CFBD's "
             "post-game home (the label), pregame_listing_* against CFBD's home in the latest payload before kickoff "
             "(unknown: that home is neither of the label's teams); cfbd = the latest saved payload fetched before "
             "kickoff, by CFBD game id; kalshi = odds_snapshots source 'kalshi' before kickoff, and "
             "kalshi_settled_markets series KXNCAAFGAME. No score, result or rate is read or printed.")
    return L
