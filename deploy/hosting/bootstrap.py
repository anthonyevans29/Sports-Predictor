#!/usr/bin/env python3
"""H1a FRESH BOOTSTRAP (architect, 2026-09-27): the host builds its OWN
database from the providers. No data travels.

    LAPTOP  bootstrap.py fingerprint --out fp_laptop.json
            Read-only counts per (sport, competition, season, status) and teams
            per (competition, season). Counts only, never rows: it is a receipt,
            not data. It is also the stored truth for which (competition, season)
            pairs exist and their season strings (law 1: never assumed).
    HOST    bootstrap.py plan --reference fp_laptop.json         (prints; runs nothing)
    HOST    bootstrap.py run  --reference fp_laptop.json [--from N]
            The standard wiring sequence per family:
              init-db -> sync-competitions per sport -> per (comp, season):
              sync-teams -> sync-matches -> the market day-one block.
            The market day-one block: a first sync-odds for every in-season
            competition, plus every Kalshi sync. Bid/ask are stored by the K1
            sync path. Accumulation then continues via the timers.
            Metered calls are used freely here as a ONE-TIME spend. Daily
            metered mode still waits on the H0-16 dashboard receipt.
    HOST    bootstrap.py fingerprint --out fp_host.json
    EITHER  bootstrap.py compare fp_laptop.json fp_host.json  -> PASS/FAIL

Phase-1 acceptance (compare):
- Every COMPLETED (competition, season) must match the laptop EXACTLY, on
  total games and on FINISHED games. "Completed" means not the newest season
  that competition has in the reference.
- The BACKLOG certification anchors must hold (see ANCHORS).
- Current seasons are reported but informational: both sides move.
- Ties and partials are FAIL; each mismatch needs an explanation (provider
  correction or pagination) logged in BACKLOG.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_common as c  # noqa: E402

# The per-family certification fingerprints on record in BACKLOG.md. "eq" is
# an exact completed-season count. "ge" is a floor: the total at
# certification time, when the live season has only grown since.
ANCHORS = [
    # NHL FOUNDATION CERTIFIED round 3, 2026-09-24
    {"label": "NHL 2024 FINISHED", "comp": "NHL", "season": "2024", "status": "FINISHED", "eq": 1502},
    {"label": "NHL 2024 CANCELLED", "comp": "NHL", "season": "2024", "status": "CANCELLED", "eq": 1},
    {"label": "NHL 2025 FINISHED", "comp": "NHL", "season": "2025", "status": "FINISHED", "eq": 1498},
    {"label": "NHL 3-season games (2026-09-23)", "comp": "NHL", "ge": 4410},
    {"label": "NHL franchises", "comp": "NHL", "teams_ge": 32},
    # NCAA CERTIFIED FIRST-AUDIT 2026-09-25
    {"label": "NCAA 3-season games (2026-09-25)", "comp": "NCAA", "ge": 9245},
    {"label": "NCAA programs", "comp": "NCAA", "teams_ge": 743},
    # NFL PHASE 1b 2026-09-05
    {"label": "NFL 3-season games (2026-09-05)", "comp": "NFL", "ge": 989},
    {"label": "NFL teams", "comp": "NFL", "teams_ge": 32},
    # v22 pot, 2026-09-21: 16,546 finished matches over the 24 competitions
    {"label": "Soccer FINISHED pot (v22, 2026-09-21)", "sport": "SOCCER", "status": "FINISHED", "ge": 16546},
    # MLB: no certification fingerprint in BACKLOG. The laptop reference is
    # the only yardstick (completed seasons exact).
]
SPORT_CLI = {"SOCCER": "soccer", "MLB": "mlb", "NFL": "nfl", "NHL": "nhl"}  # sync-competitions choices
FAMILY_ORDER = ["MLB", "NFL", "NHL", "SOCCER"]
IN_PLAY = ("SCHEDULED", "LIVE", "POSTPONED")


def fingerprint(db: Path) -> dict:
    con = c.ro_connect(db)
    try:
        games = [dict(zip(("sport", "comp", "season", "status", "n"), r)) for r in con.execute(
            "SELECT c.sport, c.code, m.season, m.status, COUNT(*) FROM matches m "
            "JOIN competitions c ON c.id = m.competition_id "
            "GROUP BY c.sport, c.code, m.season, m.status ORDER BY 1, 2, 3, 4")]
        teams = [dict(zip(("comp", "season", "n"), r)) for r in con.execute(
            "SELECT c.code, ct.season, COUNT(DISTINCT ct.team_id) FROM competition_teams ct "
            "JOIN competitions c ON c.id = ct.competition_id GROUP BY c.code, ct.season")]
        family_teams = {r[0]: r[1] for r in con.execute(
            "SELECT c.code, COUNT(DISTINCT ct.team_id) FROM competition_teams ct "
            "JOIN competitions c ON c.id = ct.competition_id GROUP BY c.code")}
        odds = {r[0] or "?": r[1] for r in con.execute(
            "SELECT source, COUNT(*) FROM odds_snapshots GROUP BY source")}
    finally:
        con.close()
    return {"created": c.iso(), "host": c.host_name(), "games": games, "teams": teams,
            "family_teams": family_teams, "odds_snapshots_by_source": odds}


def pairs(ref: dict) -> list[tuple[str, str, str]]:
    """(sport, comp, season) in the reference, families in FAMILY_ORDER,
    oldest season first."""
    seen = sorted({(g["sport"], g["comp"], g["season"]) for g in ref["games"]},
                  key=lambda t: (FAMILY_ORDER.index(t[0]) if t[0] in FAMILY_ORDER else 99, t[1], t[2]))
    return seen


def newest_season(ref: dict) -> dict:
    out: dict = {}
    for g in ref["games"]:
        out[g["comp"]] = max(out.get(g["comp"], g["season"]), g["season"])
    return out


def plan(ref: dict) -> list[list[str]]:
    steps = [["init-db"]]
    sports = [s for s in FAMILY_ORDER if any(p[0] == s for p in pairs(ref))]
    unknown = {p[0] for p in pairs(ref)} - set(SPORT_CLI)
    if unknown:
        raise SystemExit(f"✗ reference has sports with no sync-competitions route: {unknown}")
    steps += [["sync-competitions", "--sport", SPORT_CLI[s]] for s in sports]
    for _sport, comp, season in pairs(ref):
        steps.append(["sync-teams", "--competition", comp, "--season", season])
        steps.append(["sync-matches", "--competition", comp, "--season", season])
    # market day-one block: first book prices for every in-season competition
    newest = newest_season(ref)
    live = sorted({(g["sport"], g["comp"]) for g in ref["games"]
                   if g["status"] in IN_PLAY and g["season"] == newest[g["comp"]]})
    for sport, comp in live:
        if sport == "NFL":
            continue  # NFL + NCAA books come from sync-odds-football below
        steps.append(["sync-odds", "--competition", comp, "--season", newest[comp]])
    if any(s == "NFL" for s, _ in live):
        steps.append(["sync-odds-football"])
    steps += [["sync-kalshi"], ["sync-kalshi-soccer"], ["sync-kalshi-nfl"],
              ["sync-kalshi-nhl"], ["sync-kalshi-ncaa"]]
    return steps


def compare(lap: dict, host: dict) -> tuple[bool, list[str]]:
    lines, ok = [], True

    def idx(fp):
        d: dict = {}
        for g in fp["games"]:
            d.setdefault((g["comp"], g["season"]), {})[g["status"]] = g["n"]
        return d
    L, H = idx(lap), idx(host)
    newest = newest_season(lap)
    for key in sorted(L):
        lt, ht = sum(L[key].values()), sum(H.get(key, {}).values())
        lf, hf = L[key].get("FINISHED", 0), H.get(key, {}).get("FINISHED", 0)
        completed = key[1] != newest[key[0]]
        good = (lt == ht and lf == hf) if completed else True
        ok &= good
        tag = ("✓" if good else "✗") if completed else "·"
        lines.append(f"{tag} {key[0]:5s} {key[1]:8s} total {lt:>6} vs {ht:>6}  FINISHED {lf:>6} vs {hf:>6}"
                     + ("" if completed else "  (current season, informational)"))
    for key in sorted(set(H) - set(L)):
        lines.append(f"· {key[0]:5s} {key[1]:8s} host-only ({sum(H[key].values())} games)")

    for a in ANCHORS:
        rows = [g for g in host["games"]
                if (a.get("comp") in (None, g["comp"])) and (a.get("sport") in (None, g["sport"]))
                and (a.get("season") in (None, g["season"])) and (a.get("status") in (None, g["status"]))]
        if "teams_ge" in a:
            got, want, good = host["family_teams"].get(a["comp"], 0), a["teams_ge"], None
            good = got >= want
            rel = ">="
        else:
            got = sum(g["n"] for g in rows)
            want = a.get("eq", a.get("ge"))
            good = got == want if "eq" in a else got >= want
            rel = "==" if "eq" in a else ">="
        ok &= good
        lines.append(f"{'✓' if good else '✗'} ANCHOR {a['label']}: host {got} {rel} {want}")
    return ok, lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="H1a fresh bootstrap + acceptance fingerprints.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fingerprint")
    f.add_argument("--out", type=Path, required=True)
    for name in ("plan", "run"):
        p = sub.add_parser(name)
        p.add_argument("--reference", type=Path, required=True)
        if name == "run":
            p.add_argument("--from", dest="start", type=int, default=1)
    cmp = sub.add_parser("compare")
    cmp.add_argument("laptop", type=Path)
    cmp.add_argument("host", type=Path)
    a = ap.parse_args(argv)
    c.load_host_env()

    if a.cmd == "fingerprint":
        c.refuse_under_data(a.out.parent)
        fp = fingerprint(c.db_path())
        a.out.write_text(json.dumps(fp, indent=1))
        tot = sum(g["n"] for g in fp["games"])
        print(f"✓ fingerprint {a.out}: {tot} games, {len({(g['comp'], g['season']) for g in fp['games']})} "
              f"competition-seasons, odds_snapshots {fp['odds_snapshots_by_source']}")
        return 0
    if a.cmd == "compare":
        ok, lines = compare(json.loads(a.laptop.read_text()), json.loads(a.host.read_text()))
        print("\n".join(lines))
        print(f"\n{'PASS' if ok else 'FAIL'} — H1a phase-1 acceptance (completed seasons exact + anchors)")
        c.append_receipt({"kind": "bootstrap", "step": "compare", "exit": 0 if ok else 1,
                          "fails": [x for x in lines if x.startswith("✗")][:40]})
        return 0 if ok else 1

    ref = json.loads(a.reference.read_text())
    steps = plan(ref)
    if a.cmd == "plan":
        for i, st in enumerate(steps, 1):
            print(f"{i:3d}. python cli.py {' '.join(st)}")
        return 0

    import sp_run
    if c.db_path().exists() and a.start == 1:
        raise SystemExit(f"✗ {c.db_path()} already exists — bootstrap is for a FRESH host. "
                         f"Resume a partial run with --from N.")
    run_id = f"{c.utc_now().strftime('%Y%m%dT%H%M%SZ')}-bootstrap"
    ok = 0
    with c.db_lock():
        for i, st in enumerate(steps, 1):
            if i < a.start:
                continue
            line = f"python cli.py {' '.join(st)}"
            print(f"\n=== [bootstrap {i}/{len(steps)}] {line}", flush=True)
            rc, tail, dur = sp_run.run_step(st, run_id)
            c.append_receipt({"kind": "step", "unit": "bootstrap", "run_id": run_id, "step": i,
                              "command": line, "exit": rc, "duration_s": round(dur, 1),
                              "tail": tail})
            if rc != 0:
                print(f"\n✗ step {i} failed (exit {rc}). Fix, then resume: bootstrap.py run "
                      f"--reference {a.reference} --from {i}")
                c.append_receipt({"kind": "chain", "unit": "bootstrap", "run_id": run_id,
                                  "exit": rc, "steps_ok": ok, "steps_total": len(steps)})
                return rc
            ok += 1
    c.append_receipt({"kind": "chain", "unit": "bootstrap", "run_id": run_id, "exit": 0,
                      "steps_ok": ok, "steps_total": len(steps),
                      "counts": c.table_counts(c.db_path(), c.CHAIN_COUNT_TABLES)})
    print(f"\n✓ bootstrap: {ok} steps. Next: fingerprint --out fp_host.json, then compare.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
