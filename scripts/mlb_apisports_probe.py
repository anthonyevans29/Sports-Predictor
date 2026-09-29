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
      against our status on paired games, plus score agreement on finished pairs.
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
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TOL_H = 12
OUR_POSTSEASON = {"F", "D", "L", "W"}          # statsapi gameType: wildcard/division/LCS/WS
CANDIDATE_TYPE_FIELDS = ("week", "stage", "type", "round", "game_type")


def _norm(name: str) -> str:
    from src.ingestion.match_lookup import normalize_team_name
    return normalize_team_name(name or "")


def _names_match(a: str, b: str) -> bool:
    return a == b or (a and b and (a in b or b in a))


def provider_rows(games: list[dict]) -> list[dict]:
    """Flatten /games items into {id, utc, home, away, status_short, status_long,
    home_runs, away_runs, extra}. `extra` keeps every candidate type field present."""
    out = []
    for g in games or []:
        teams = g.get("teams") or {}
        st = g.get("status") or {}
        sc = g.get("scores") or {}
        try:
            utc = datetime.fromisoformat(str(g.get("date")).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            utc = None
        out.append({"id": g.get("id"), "utc": utc,
                    "home": (teams.get("home") or {}).get("name"),
                    "away": (teams.get("away") or {}).get("name"),
                    "status_short": st.get("short"), "status_long": st.get("long"),
                    "home_runs": (sc.get("home") or {}).get("total"),
                    "away_runs": (sc.get("away") or {}).get("total"),
                    "extra": {k: g.get(k) for k in CANDIDATE_TYPE_FIELDS if k in g}})
    return out


def pair(ours: list[dict], prov: list[dict]) -> dict:
    """Pair our matches with provider games: same normalized home/away names and
    kickoff within +/-TOL_H hours; among several candidates (doubleheaders) the
    nearest start wins, and a tie is AMBIGUOUS (counted, left unpaired).
    ours rows: {id, utc, home, away, status, stage, home_score, away_score}."""
    by_pair: dict[tuple, list[dict]] = {}
    for p in prov:
        if p["utc"] is None:
            continue
        by_pair.setdefault((_norm(p["home"]), _norm(p["away"])), []).append(p)
    used, pairs, unmatched, ambiguous = set(), [], [], []
    for o in sorted(ours, key=lambda r: r["utc"]):
        h, a = _norm(o["home"]), _norm(o["away"])
        cands = [p for (ph, pa), ps in by_pair.items() if _names_match(h, ph) and _names_match(a, pa)
                 for p in ps if p["id"] not in used and abs((p["utc"] - o["utc"]).total_seconds()) <= TOL_H * 3600]
        if not cands:
            unmatched.append(o)
            continue
        cands.sort(key=lambda p: abs((p["utc"] - o["utc"]).total_seconds()))
        if len(cands) > 1 and abs((cands[0]["utc"] - o["utc"]).total_seconds()) == \
                abs((cands[1]["utc"] - o["utc"]).total_seconds()):
            ambiguous.append(o)
            continue
        used.add(cands[0]["id"])
        pairs.append((o, cands[0]))
    return {"pairs": pairs, "ours_unmatched": unmatched, "ambiguous": ambiguous,
            "provider_unmatched": [p for p in prov if p["id"] not in used]}


def summarize(season: str, ours: list[dict], prov: list[dict], odds_match_ids: set) -> dict:
    r = pair(ours, prov)
    P = r["pairs"]
    fin = [(o, p) for o, p in P if o["status"] == "FINISHED" and o["home_score"] is not None
           and p["home_runs"] is not None]
    score_ok = sum(1 for o, p in fin if (o["home_score"], o["away_score"]) == (p["home_runs"], p["away_runs"]))
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
        out.append(f"{'✓' if s['score_agree'] == s['finished_pairs_scored'] else '✗'} scores {s['season']}: "
                   f"{s['score_agree']}/{s['finished_pairs_scored']} finished pairs agree")
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
    report = {"generated": datetime.utcnow().isoformat() + "Z", "league_id": MLB_LEAGUE_ID,
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
                  "finished_pairs_scored", "score_agree", "postseason_ours", "postseason_paired",
                  "stage_vs_provider_fields", "odds_joined_matches", "odds_joined_paired", "id_sample"):
            print(f"  {k}: {s[k]}")
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
