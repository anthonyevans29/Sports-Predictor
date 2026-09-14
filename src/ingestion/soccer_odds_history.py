"""
Historical closing-odds ingest from football-data.co.uk (free CSVs).

WHY: joins the leakage-free soccer backtest to REAL closing prices, giving
soccer an honest model-vs-market read (CLV analog, market log-loss baseline)
across a whole past season BEFORE any live prediction ships. The MLB side
never had this pre-launch — its CLV verdict took weeks of forward data.

Source format: one CSV per league-season, e.g.
  https://www.football-data.co.uk/mmz4281/2425/E0.csv   (E0 = Premier League)
Columns of interest: Date, HomeTeam, AwayTeam, and closing 1X2 prices —
preferred source order: Pinnacle closing (PSCH/PSCD/PSCA), then Bet365 closing
(B365CH/B365CD/B365CA), then market-average closing (AvgCH/AvgCD/AvgCA).
Older seasons lack closing columns entirely; those rows are counted and
skipped (no silent fallback to open prices — CLV against opens is not CLV).

Rows are matched to DB games by DATE (±1 day, kickoff-timezone slack) plus
BOTH team names via synonym-expanded token overlap (team_aliases). Ambiguity
is refused and reported, never guessed — same three-gate philosophy as the
Kalshi matcher.

Stored as Odds rows: bookmaker="fdcuk_close" (plus a *_src note of which
source column won), market="1X2", selection HOME/DRAW/AWAY, is_closing=True.
Idempotent: an existing (match, fdcuk_close, 1X2) trio is skipped on re-run.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from src.db.database import session_scope
from src.db.schema import Competition, Match, MatchStatus, Odds, Sport
from src.ingestion.team_aliases import team_match_score

log = logging.getLogger(__name__)

BOOKMAKER = "fdcuk_close"
# (label, home_col, draw_col, away_col) in preference order
CLOSING_SOURCES = [
    ("pinnacle", "PSCH", "PSCD", "PSCA"),
    ("bet365", "B365CH", "B365CD", "B365CA"),
    ("avg", "AvgCH", "AvgCD", "AvgCA"),
]


def season_to_url(season: str, league_code: str = "E0") -> str:
    """DB season string -> football-data.co.uk CSV URL.
    "2024" or "2024/25" or "2024-2025" -> mmz4281/2425/E0.csv"""
    digits = "".join(ch for ch in season if ch.isdigit())
    y1 = int(digits[:4])
    yy1, yy2 = y1 % 100, (y1 + 1) % 100
    return (f"https://www.football-data.co.uk/mmz4281/"
            f"{yy1:02d}{yy2:02d}/{league_code}.csv")


def _parse_date(raw: str):
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


def _pick_closing(row: dict):
    """Return (label, oh, od, oa) from the first fully-present closing source."""
    for label, ch, cd, ca in CLOSING_SOURCES:
        try:
            oh, od, oa = float(row[ch]), float(row[cd]), float(row[ca])
            if oh > 1.0 and od > 1.0 and oa > 1.0:
                return label, oh, od, oa
        except (KeyError, ValueError, TypeError):
            continue
    return None


def sync_soccer_closing_odds(
    competition_code: str = "PL",
    season: str | None = None,
    csv_path: str | None = None,
    url: str | None = None,
    progress=None,
) -> dict:
    """
    Ingest one season's closing odds. Provide csv_path (a downloaded file) or
    url (fetched with requests); if neither, the URL is derived from `season`.
    """
    def say(msg):
        if progress:
            progress(msg)

    if csv_path:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            text = f.read()
    else:
        import requests
        fetch_url = url or season_to_url(season or "")
        say(f"Fetching {fetch_url} …")
        resp = requests.get(fetch_url, timeout=30)
        resp.raise_for_status()
        text = resp.content.decode("utf-8-sig", errors="replace")

    rows = list(csv.DictReader(io.StringIO(text)))
    say(f"CSV rows: {len(rows)}")

    with session_scope() as s:
        comp = s.execute(
            select(Competition).where(Competition.code == competition_code)
        ).scalar_one_or_none()
        if not comp:
            return {"ok": False, "reason": f"competition {competition_code} not in DB"}

        q = select(Match).where(Match.competition_id == comp.id)
        if season:
            q = q.where(Match.season == season)
        matches = [m for m in s.execute(q).scalars() if m.utc_date]

        # index matches by date for the date gate (±1 day slack: CSV dates are
        # local UK; DB kickoff is UTC and late kickoffs can cross midnight)
        by_date: dict = {}
        for m in matches:
            by_date.setdefault(m.utc_date.date(), []).append(m)

        existing = set(
            s.execute(
                select(Odds.match_id).where(
                    Odds.bookmaker == BOOKMAKER, Odds.market == "1X2"
                )
            ).scalars()
        )

        stored = skipped_existing = unmatched = ambiguous = no_closing = 0
        unmatched_names = []

        for row in rows:
            d = _parse_date(row.get("Date", ""))
            ht, at = row.get("HomeTeam", ""), row.get("AwayTeam", "")
            if not d or not ht or not at:
                continue
            closing = _pick_closing(row)
            if closing is None:
                no_closing += 1
                continue
            label, oh, od, oa = closing

            candidates = []
            for delta in (-1, 0, 1):
                candidates.extend(by_date.get(d + timedelta(days=delta), []))

            best, best_score, tie = None, 0, False
            for m in candidates:
                if not (m.home_team and m.away_team):
                    continue
                hs = team_match_score(ht, m.home_team.name)
                as_ = team_match_score(at, m.away_team.name)
                if hs < 1 or as_ < 1:
                    continue
                score = hs + as_
                if score > best_score:
                    best, best_score, tie = m, score, False
                elif score == best_score and best is not None and m.id != best.id:
                    tie = True
            if best is None or tie:
                unmatched += 1
                if tie:
                    ambiguous += 1
                if len(unmatched_names) < 10:
                    unmatched_names.append(f"{ht} v {at} ({d})")
                continue

            if best.id in existing:
                skipped_existing += 1
                continue

            for sel, price in (("HOME", oh), ("DRAW", od), ("AWAY", oa)):
                s.add(Odds(
                    match_id=best.id, bookmaker=BOOKMAKER, market="1X2",
                    selection=sel, price_decimal=price, line=None,
                    is_opening=False, is_closing=True,
                    source=f"football-data-uk:{label}",
                ))
            existing.add(best.id)
            stored += 1

        return {
            "ok": True, "csv_rows": len(rows), "stored_games": stored,
            "skipped_existing": skipped_existing, "unmatched": unmatched,
            "ambiguous": ambiguous, "no_closing_cols": no_closing,
            "unmatched_sample": unmatched_names,
        }
