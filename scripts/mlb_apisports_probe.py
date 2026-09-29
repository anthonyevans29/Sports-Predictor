"""
MLB-PROBE (architect, 2026-09-29) — read-only, zero wiring.

Question: can api-sports BASEBALL's /games replace statsapi.mlb.com for MLB
schedule/results on the host? statsapi returns 406 to datacenter ASNs, so MLB
syncing is a laptop duty today; this is the durable-fix reconnaissance.

Run it on the LAPTOP (the DB with the statsapi-synced MLB seasons):

    python3 scripts/mlb_apisports_probe.py [--seasons 2025 2026] [--out receipt.json]

It answers, with receipts:
  Q0  plan reach + season-string format: /leagues?id=1 (the adapter's MLB_LEAGUE_ID)
  Q1  COVERAGE: per season, our MLB matches vs the provider's games, paired by
      (kickoff +/-12h, normalized team names). This is the same join sync-odds MLB
      uses (src.ingestion.match_lookup), in memory. Doubleheaders pair on the
      nearest start time; anything left ambiguous is COUNTED, never guessed.
  Q2  ID MAPPING via the odds join: the matches that already carry api_baseball
      odds were joined to a provider game by that same rule. The probe checks they
      pair 1:1 here too, and prints the provider id -> match id sample (a durable
      external id the host could key on).
  Q3  STATUS VOCABULARY: provider status short/long values, cross-tabbed
      against our status on paired games, plus SCORE PARITY on finished pairs
      (scores.home/away.total vs ours) — the PHASE A gate (>= 99.5%, architect
      2026-09-29) — with a sample of any disagreements, and every unpaired
      FINISHED game of ours by name/date with a doubleheader / UTC-boundary
      suspect read.
  Q4  POSTSEASON: our stage (gameType R/F/D/L/W) cross-tabbed against every
      provider field that could carry a game type. The fields are enumerated
      from the response (law 1), never assumed.

Provider cost: 1 + one /games call per season (3 calls for 2025+2026).
Database: read-only. Writes nothing unless --out is given, and never under data/.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ingestion.mlb_apisports import (  # noqa: E402 — the ONE pairing definition (PHASE A shares it)
    CANDIDATE_TYPE_FIELDS, SUSPECT_H, TOL_H, pair, provider_rows, suspects,
)

SCORE_GATE_PCT = 99.5   # architect 2026-09-29: score parity >= 99.5% gates PHASE A


def _finished(status) -> bool:
    """Our status as the DB stores it: MatchStatus.FINISHED.value == "finished"
    (lowercase). The first probe compared against "FINISHED" and so never
    scored a pair (receipt 2026-09-29): the vocabulary is read, not assumed."""
    return str(getattr(status, "value", status)).lower() == "finished"
OUR_POSTSEASON = {"F", "D", "L", "W"}          # statsapi gameType: wildcard/division/LCS/WS


def summarize(season: str, ours: list[dict], prov: list[dict], odds_match_ids: set) -> dict:
    r = pair(ours, prov)
    P = r["pairs"]
    fin = [(o, p) for o, p in P if _finished(o["status"]) and o["home_score"] is not None
           and p["home_runs"] is not None]
    agree = lambda o, p: (o["home_score"], o["away_score"]) == (p["home_runs"], p["away_runs"])
    score_ok = sum(1 for o, p in fin if agree(o, p))
    unpaired_fin = [o for o in r["ours_unmatched"] + r["ambiguous"] if _finished(o["status"])]
    paired_ids = {o["id"] for o, _ in P}
    stage_x = Counter((o["stage"] or "?", json.dumps(p["extra"], sort_keys=True, default=str)) for o, p in P)
    return {
        "season": season, "ours": len(ours), "provider": len(prov),
        "paired": len(P), "coverage_pct": round(100 * len(P) / len(ours), 2) if ours else None,
        "ours_unmatched": len(r["ours_unmatched"]),
        "ours_unmatched_by_stage_status": dict(Counter(f"{o['stage']}/{o['status']}" for o in r["ours_unmatched"])),
        "ambiguous": len(r["ambiguous"]),
        "provider_unmatched": len(r["provider_unmatched"]),
        "provider_unmatched_by_status": dict(Counter(p["status_short"] for p in r["provider_unmatched"])),
        "status_vocab": dict(Counter(f"{p['status_short']}|{p['status_long']}" for p in prov)),
        "status_crosstab": dict(Counter(f"{o['status']} <- {p['status_short']}" for o, p in P)),
        "finished_pairs_scored": len(fin), "score_agree": score_ok,
        "score_parity_pct": round(100 * score_ok / len(fin), 2) if fin else None,
        "score_disagree_sample": [{"match_id": o["id"], "provider_id": p["id"], "game": f"{o['away']} @ {o['home']}",
                                   "utc": o["utc"].isoformat(), "ours": f"{o['away_score']}-{o['home_score']}",
                                   "provider": f"{p['away_runs']}-{p['home_runs']}"}
                                  for o, p in fin if not agree(o, p)][:15],
        "ours_unpaired_finished": suspects(unpaired_fin, prov, r["paired_to"]),
        "postseason_ours": sum(1 for o in ours if o["stage"] in OUR_POSTSEASON),
        "postseason_paired": sum(1 for o, _ in P if o["stage"] in OUR_POSTSEASON),
        "stage_vs_provider_fields": {f"{k[0]} | {k[1]}": n for k, n in sorted(stage_x.items())},
        "odds_joined_matches": len(odds_match_ids),
        "odds_joined_paired": len(odds_match_ids & paired_ids),
        "id_sample": [{"provider_id": p["id"], "match_id": o["id"], "utc": o["utc"].isoformat()}
                      for o, p in P[:5]],
    }


def verdict(s: dict) -> list[str]:
    out = []
    cov = s["coverage_pct"]
    out.append(f"{'✓' if cov is not None and cov >= 99.5 else '✗'} coverage {s['season']}: "
               f"{s['paired']}/{s['ours']} ({cov}%) · ambiguous {s['ambiguous']} · provider-only {s['provider_unmatched']}")
    if s["finished_pairs_scored"]:
        pct = s["score_parity_pct"]
        out.append(f"{'✓' if pct >= SCORE_GATE_PCT else '✗'} scores {s['season']}: "
                   f"{s['score_agree']}/{s['finished_pairs_scored']} finished pairs agree ({pct}%) — "
                   f"PHASE A gate >= {SCORE_GATE_PCT}%: {'PASS' if pct >= SCORE_GATE_PCT else 'FAIL'}")
    else:
        out.append(f"✗ scores {s['season']}: no finished pair scored — the PHASE A gate cannot be evaluated")
    if s.get("ours_unpaired_finished"):
        out.append(f"· {len(s['ours_unpaired_finished'])} of our FINISHED games unpaired (listed above)")
    if s["postseason_ours"]:
        out.append(f"{'✓' if s['postseason_paired'] == s['postseason_ours'] else '✗'} postseason {s['season']}: "
                   f"{s['postseason_paired']}/{s['postseason_ours']} of our F/D/L/W games paired")
    if s["odds_joined_matches"]:
        out.append(f"{'✓' if s['odds_joined_paired'] == s['odds_joined_matches'] else '✗'} odds-join ids {s['season']}: "
                   f"{s['odds_joined_paired']}/{s['odds_joined_matches']} odds-joined matches pair here")
    return out


def _ours(season: str) -> tuple[list[dict], set]:
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Competition, Match, Odds, Sport
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.sport == Sport.MLB,
                                                   Competition.code == "MLB")).scalars().first()
        if comp is None:
            raise SystemExit("✗ no MLB competition in this DB — run the probe on the laptop.")
        rows = []
        for m in s.execute(select(Match).where(Match.competition_id == comp.id,
                                               Match.season == season)).scalars():
            rows.append({"id": m.id, "utc": m.utc_date, "home": m.home_team.name, "away": m.away_team.name,
                         "status": getattr(m.status, "value", str(m.status)), "stage": m.stage,
                         "home_score": m.home_score, "away_score": m.away_score})
        ids = {r["id"] for r in rows}
        odds = {mid for (mid,) in s.execute(select(Odds.match_id).where(
            Odds.source == "api_baseball", Odds.match_id.in_(ids or {-1})).distinct())}
    return rows, odds


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="MLB-PROBE: api-sports Baseball /games vs our statsapi MLB (read-only)")
    ap.add_argument("--seasons", nargs="+", default=["2025", "2026"])
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from src.adapters.api_baseball import MLB_LEAGUE_ID, APIBaseballClient
    cl = APIBaseballClient.from_env()
    if cl is None:
        print("✗ No API-Baseball key (API_BASEBALL_KEY / API_FOOTBALL_KEY). Stop.")
        return 1
    lg = (cl._get("leagues", params={"id": MLB_LEAGUE_ID}).get("response") or [{}])[0]
    seasons_avail = [x.get("season") for x in (lg.get("seasons") or [])]
    print(f"Q0 league id={MLB_LEAGUE_ID} name={(lg.get('league') or lg).get('name')!r} "
          f"seasons tail={seasons_avail[-4:]} (format receipt)")
    report = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "league_id": MLB_LEAGUE_ID,
              "seasons_available": seasons_avail, "seasons": []}
    for season in a.seasons:
        games = cl._get("games", params={"league": MLB_LEAGUE_ID, "season": int(season)}).get("response") or []
        keys = sorted({k for g in games for k in g})
        print(f"\nSEASON {season}: provider /games returned {len(games)} · item keys {keys}")
        ours, odds_ids = _ours(season)
        s = summarize(season, ours, provider_rows(games), odds_ids)
        s["provider_item_keys"] = keys
        for k in ("paired", "coverage_pct", "ours_unmatched", "ours_unmatched_by_stage_status", "ambiguous",
                  "provider_unmatched", "provider_unmatched_by_status", "status_vocab", "status_crosstab",
                  "finished_pairs_scored", "score_agree", "score_parity_pct", "postseason_ours", "postseason_paired",
                  "stage_vs_provider_fields", "odds_joined_matches", "odds_joined_paired", "id_sample"):
            print(f"  {k}: {s[k]}")
        for d in s["score_disagree_sample"]:
            print(f"  ✗ score differs: {d['game']} {d['utc'][:16]} ours {d['ours']} vs provider {d['provider']} "
                  f"(match #{d['match_id']}, provider #{d['provider_id']})")
        for u in s["ours_unpaired_finished"]:
            print(f"  ? unpaired FINISHED: {u['game']} {u['utc'][:16]} stage {u['stage']} {u['score']} "
                  f"(match #{u['match_id']}) — {u['why']}")
        for v in verdict(s):
            print(f"  {v}")
        report["seasons"].append(s)
    print(f"\nprovider requests remaining: {cl.requests_remaining}")
    if a.out:
        if "data" in a.out.resolve().parts:
            print("✗ refusing to write under data/ (law 5).")
            return 1
        a.out.write_text(json.dumps(report, indent=1, default=str))
        print(f"✓ receipt written to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
