"""
RESYNC-DIFF — read-only: does the provider's CURRENT listing differ from our
STORED rows? (architect ruling 2026-10-01, NCAA audit: "if the provider's
current data differs from our stored rows, our ingestion-era copy was bad and
the re-sync repairs it; if it matches, the provider's 2025 labels are wrong at
source.")

WHY A DIFF AND NOT A RE-SYNC (law 1, found 2026-10-01): sync-matches'
_apply_match_updates refreshes status / season / stage / date / SCORES on an
existing row but NEVER its home_team_id / away_team_id. If the provider's
labels now disagree with ours, a re-sync cannot repair the labels — it would
write the provider's home score onto OUR home team, flipping the stored
result. So the question is answered by comparing, writing nothing; any repair
is a separate, ruled step.

Per provider listing (keyed on the provider's match id = our external_ids
[source]):
  teams   same | swapped | different          (by the provider's team ids)
  scores  same | swapped | different | provider_missing | ours_missing
  date    moved > 1h
plus provider rows not in our DB, our rows the listing no longer carries, and
the HOME WIN RATE of the matched finished games under OUR labels vs the
PROVIDER's (the audit's own statistic, recomputed on both copies).
"""
from __future__ import annotations

from collections import Counter
from datetime import timedelta


def _cls_pair(ours: tuple, prov: tuple) -> str:
    if ours == prov:
        return "same"
    if ours == (prov[1], prov[0]):
        return "swapped"
    return "different"


def classify_row(ours: dict, nm) -> dict:
    """Pure. ours: {home_src, away_src, home_score, away_score, utc_date};
    nm: the provider's NormalizedMatch-like object."""
    teams = _cls_pair((ours["home_src"], ours["away_src"]),
                      (str(nm.home_team_source_id), str(nm.away_team_source_id)))
    if nm.home_score is None or nm.away_score is None:
        scores = "provider_missing"
    elif ours["home_score"] is None or ours["away_score"] is None:
        scores = "ours_missing"
    else:
        scores = _cls_pair((ours["home_score"], ours["away_score"]), (nm.home_score, nm.away_score))
    moved = (ours["utc_date"] is not None and nm.utc_date is not None
             and abs(ours["utc_date"] - nm.utc_date) > timedelta(hours=1))
    return {"teams": teams, "scores": scores, "date_moved": moved}


def diff(adapter, competition_code: str, season: str | None, date_from: str | None = None,
         date_to: str | None = None, sample: int = 12) -> dict:
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, Team

    listing = adapter.list_matches(competition_code, season, date_from, date_to)
    rc, samples = Counter(), {}
    home_rate = {"ours": [0, 0], "provider": [0, 0]}          # [home wins, decided]
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == competition_code)).scalar_one_or_none()
        if comp is None:
            return {"error": f"competition {competition_code} not in DB"}
        source = listing[0].source if listing else None
        q = select(Match).where(Match.competition_id == comp.id)
        if season:
            q = q.where(Match.season == season)
        ours = {}
        for m in (s.execute(q).scalars() if source else []):
            eid = (m.external_ids or {}).get(source)
            if eid is not None:
                ours[str(eid)] = m
        team_src = {t.id: (t.external_ids or {}).get(source) for t in
                    s.execute(select(Team).where(Team.sport == comp.sport)).scalars()}
        names = {t.id: t.name for t in s.execute(select(Team).where(Team.sport == comp.sport)).scalars()}
        seen = set()
        for nm in listing:
            m = ours.get(str(nm.source_id))
            if m is None:
                rc["provider_only"] += 1
                continue
            seen.add(str(nm.source_id))
            row = classify_row({"home_src": str(team_src.get(m.home_team_id)),
                                "away_src": str(team_src.get(m.away_team_id)),
                                "home_score": m.home_score, "away_score": m.away_score,
                                "utc_date": m.utc_date}, nm)
            rc["matched"] += 1
            rc[f"teams_{row['teams']}"] += 1
            rc[f"scores_{row['scores']}"] += 1
            rc["date_moved"] += row["date_moved"]
            if row["teams"] != "same" or row["scores"] not in ("same", "provider_missing"):
                key = f"teams {row['teams']} / scores {row['scores']}"
                samples.setdefault(key, []).append(
                    f"{m.utc_date:%Y-%m-%d} match {m.id} ours {names.get(m.away_team_id)} @ "
                    f"{names.get(m.home_team_id)} {m.away_score}-{m.home_score} · provider "
                    f"{nm.away_team_source_id}@{nm.home_team_source_id} {nm.away_score}-{nm.home_score}")
            if m.status == MatchStatus.FINISHED and m.home_score is not None and m.away_score is not None \
                    and m.home_score != m.away_score:
                home_rate["ours"][1] += 1
                home_rate["ours"][0] += m.home_score > m.away_score
            if nm.home_score is not None and nm.away_score is not None and nm.home_score != nm.away_score:
                home_rate["provider"][1] += 1
                home_rate["provider"][0] += nm.home_score > nm.away_score
        rc["ours_not_in_listing"] = len(set(ours) - seen)
    rate = {k: (round(v[0] / v[1], 3) if v[1] else None, v[1]) for k, v in home_rate.items()}
    return {"competition": competition_code, "season": season, "source": source,
            "listing": len(listing), "counts": dict(rc), "home_rate": rate,
            "samples": {k: v[:sample] for k, v in samples.items()}}


def verdict(counts: dict) -> str:
    """The ruling's question in one line, from the counts (no inference beyond them)."""
    matched = counts.get("matched", 0)
    if not matched:
        return "NO MATCHED ROWS — nothing to compare (check season string / sync-teams)"
    bad = counts.get("teams_swapped", 0) + counts.get("teams_different", 0)
    sc = counts.get("scores_swapped", 0) + counts.get("scores_different", 0)
    if bad == 0 and sc == 0:
        return ("PROVIDER MATCHES OUR ROWS — the labels are the provider's own (wrong at source "
                "if the audit's rates are implausible); a re-sync changes nothing")
    return (f"PROVIDER DIFFERS on {bad} team label(s) and {sc} score(s) of {matched} — our copy "
            f"differs from the provider's current data. NOTE: sync-matches does NOT rewrite "
            f"home/away on existing rows; a repair is a separate ruled step")
