#!/usr/bin/env python3
"""H1a FRESH BOOTSTRAP (architect, 2026-09-27): the host builds its OWN
database from the providers. No data travels.

    LAPTOP  bootstrap.py fingerprint --out fp_laptop.json
            Read-only counts per (sport, competition, season, status) and teams
            per (competition, season). Games and teams are counts only, never
            rows: it is a receipt, not data. It is also the stored truth for which (competition, season)
            pairs exist and their season strings (law 1: never assumed).
            It also carries the MODEL REGISTRY SEED (architect-ratified): the
            production model_versions rows, every column. These are model
            identities and parameters; config, not history.
    HOST    bootstrap.py plan --reference fp_laptop.json         (prints; runs nothing)
    HOST    bootstrap.py run  --reference fp_laptop.json [--from N]
            The standard wiring sequence per family:
              init-db -> seed the production model rows (no odds, no
              predictions, no grades: the host's BOOKS stay empty) ->
              sync-competitions per sport -> per (comp, season):
              sync-teams -> sync-matches -> the market day-one block.
            The market day-one block: a first sync-odds for every in-season
            competition, plus every Kalshi sync. Bid/ask are stored by the K1
            sync path. Accumulation then continues via the timers.
            Metered calls are used freely here as a ONE-TIME spend. Daily
            metered mode still waits on the H0-16 dashboard receipt.
            --skip-family MLB (repeatable): the family's sync-teams and
            sync-matches steps are SKIPPED and receipted as SKIPPED-ASN. Step
            numbers never change, so --from N still means the same step. This
            exists because statsapi.mlb.com returns 406 to datacenter ASNs
            (architect finding, 2026-09-27); MLB syncing stays a LAPTOP duty.
    HOST    bootstrap.py fingerprint --out fp_host.json
    EITHER  bootstrap.py compare fp_laptop.json fp_host.json [--skip-family MLB]  -> PASS/FAIL
            A skipped family is N/A-host (laptop-only), never a failure.
            VERSION GUARD (architect finding, 2026-09-27): every fingerprint
            embeds the producing bootstrap.py's git blob SHA. compare REFUSES
            fingerprints from different bootstrap versions, or unstamped ones,
            before comparing a single row. A pre-#42 laptop fingerprint against
            a post-#42 host one showed UEL 2024/25 as 269 vs 202 while sqlite
            held 269 on both machines: version skew, not data.
            --waive COMP:SEASON:reason (repeatable; architect ruling 2026-09-27):
            an explained provider difference on a completed season. The row
            still PRINTS, with both counts and the reason, marked WAIVED. The
            waiver is recorded in the receipt. It is for real provider drift
            ONLY, never to paper over an instrument bug (ruling 2026-09-27:
            UEL 2024/25 was fingerprint version skew, so no waiver). It is
            never hidden, and never
            applies to a matching row, which prints "waiver unused".

Phase-1 acceptance (compare):
- Every COMPLETED (competition, season) must match the laptop EXACTLY, on
  total games and on FINISHED games. "Completed" means not the newest season
  that competition has in the reference.
- The BACKLOG certification anchors must hold (see ANCHORS).
- Model identity must match: the same production version per (sport,
  family), with an identical parameters hash.
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
SEED = "__seed-model-registry__"  # a bootstrap-internal step, not a cli command


def _params_hash(raw) -> str:
    """Canonical hash of a stored parameters JSON (text in SQLite)."""
    import hashlib
    try:
        obj = json.loads(raw) if isinstance(raw, str) else raw
        canon = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        canon = str(raw)
    return hashlib.sha256(canon.encode()).hexdigest()


def model_rows(con: sqlite3.Connection) -> list[dict]:
    """Every column of the PRODUCTION model_versions rows, as stored.
    Columns are enumerated from the table itself (law 1)."""
    cols = [r[1] for r in con.execute("PRAGMA table_info(model_versions)")]
    if not cols:
        return []
    rows = [dict(zip(cols, r)) for r in con.execute(
        "SELECT * FROM model_versions WHERE status = 'production' ORDER BY sport, model_family")]
    for r in rows:
        r.pop("id", None)
        r["_params_sha256"] = _params_hash(r.get("parameters"))
    return rows


def seed_models(db: Path, rows: list[dict]) -> dict:
    """Install the reference's production model rows into the fresh DB.
    Refuses unless model_versions is empty (a seed, never a merge)."""
    if not rows:
        raise SystemExit("✗ the reference carries no production model rows — refusing to "
                         "bootstrap a host that cannot predict (re-run fingerprint on the laptop).")
    con = sqlite3.connect(db)
    try:
        have = con.execute("SELECT COUNT(*) FROM model_versions").fetchone()[0]
        if have:
            raise SystemExit(f"✗ model_versions already has {have} rows — the seed is for a fresh DB.")
        cols = {r[1] for r in con.execute("PRAGMA table_info(model_versions)")}
        for r in rows:
            keep = {k: v for k, v in r.items() if k in cols}
            missing = set(r) - cols - {"_params_sha256"}
            if missing:
                raise SystemExit(f"✗ host schema lacks model_versions columns {missing} — deploy main first.")
            con.execute(f"INSERT INTO model_versions ({', '.join(keep)}) VALUES "
                        f"({', '.join('?' * len(keep))})", list(keep.values()))
        con.commit()
        got = model_rows(con)
    finally:
        con.close()
    bad = [r["version"] for r, g in zip(sorted(rows, key=_mkey), sorted(got, key=_mkey))
           if r["_params_sha256"] != g["_params_sha256"]]
    if len(got) != len(rows) or bad:
        raise SystemExit(f"✗ seed verification failed: {len(got)}/{len(rows)} rows, hash mismatch {bad}")
    return {"seeded": [f"{r['sport']}/{r['model_family']}/{r['version']}" for r in got]}


def _mkey(r: dict) -> tuple:
    return (str(r.get("sport")), str(r.get("model_family")))


def producer_version() -> dict:
    """The producing bootstrap.py's git blob SHA (identical to `git hash-object`,
    computed from the file bytes so a local edit shows too) plus the checkout's
    commit SHA for human reference."""
    import hashlib
    data = Path(__file__).read_bytes()
    blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
    return {"bootstrap_blob_sha": blob, "git_commit": c.git_sha()}


def version_mismatch(lap: dict, host: dict) -> str | None:
    """Refusal message when the two fingerprints were made by different
    bootstrap.py versions (or either is unstamped), else None."""
    a, b = lap.get("producer") or {}, host.get("producer") or {}
    if not a.get("bootstrap_blob_sha") or not b.get("bootstrap_blob_sha"):
        who = [n for n, x in (("laptop", a), ("host", b)) if not x.get("bootstrap_blob_sha")]
        return (f"✗ REFUSED: {' and '.join(who)} fingerprint carries no bootstrap version stamp "
                f"(made before the version guard). Regenerate it on current main: "
                f"`bootstrap.py fingerprint --out ...`, then re-compare.")
    if a["bootstrap_blob_sha"] != b["bootstrap_blob_sha"]:
        return (f"✗ REFUSED: fingerprints come from different bootstrap.py versions "
                f"(laptop {a['bootstrap_blob_sha'][:12]} @ {a.get('git_commit')}, host "
                f"{b['bootstrap_blob_sha'][:12]} @ {b.get('git_commit')}). Counting rules may differ, "
                f"so a row delta could be version skew, not data. Pull main on both machines, "
                f"regenerate both fingerprints, re-compare.")
    return None


# The fingerprint's counting predicate, printed verbatim by `explain` (receipt
# request 2026-09-27). It groups by the match's own competition_id, so every row
# in `matches` lands in exactly one group. The LEFT JOIN means an orphan
# competition_id is counted under "?#<id>", never dropped. fingerprint()
# self-checks the grouped total against a raw COUNT(*) FROM matches.
FINGERPRINT_SQL = (
    "SELECT COALESCE(c.sport, '?'), COALESCE(c.code, '?#' || m.competition_id), "
    "m.season, m.status, COUNT(*) FROM matches m "
    "LEFT JOIN competitions c ON c.id = m.competition_id "
    "GROUP BY m.competition_id, m.season, m.status ORDER BY 1, 2, 3, 4")


def fingerprint(db: Path) -> dict:
    con = c.ro_connect(db)
    try:
        games = [dict(zip(("sport", "comp", "season", "status", "n"), r))
                 for r in con.execute(FINGERPRINT_SQL)]
        raw_total = con.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
        if sum(g["n"] for g in games) != raw_total:
            raise SystemExit(f"✗ fingerprint self-check failed: grouped {sum(g['n'] for g in games)} "
                             f"!= raw COUNT(*) {raw_total}")
        teams = [dict(zip(("comp", "season", "n"), r)) for r in con.execute(
            "SELECT c.code, ct.season, COUNT(DISTINCT ct.team_id) FROM competition_teams ct "
            "JOIN competitions c ON c.id = ct.competition_id GROUP BY c.code, ct.season")]
        family_teams = {r[0]: r[1] for r in con.execute(
            "SELECT c.code, COUNT(DISTINCT ct.team_id) FROM competition_teams ct "
            "JOIN competitions c ON c.id = ct.competition_id GROUP BY c.code")}
        odds = {r[0] or "?": r[1] for r in con.execute(
            "SELECT source, COUNT(*) FROM odds_snapshots GROUP BY source")}
        models = model_rows(con)
    finally:
        con.close()
    return {"created": c.iso(), "host": c.host_name(), "producer": producer_version(),
            "games": games, "raw_match_total": raw_total, "teams": teams,
            "family_teams": family_teams, "odds_snapshots_by_source": odds,
            "model_registry": models}


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


SKIP_TAG = "SKIPPED-ASN"
SKIPPABLE = ("sync-teams", "sync-matches")


def comp_sport(ref: dict) -> dict:
    return {g["comp"]: g["sport"] for g in ref["games"]}


def is_skipped(st: list[str], sports: dict, skip: set) -> bool:
    """A family's provider-sync steps (sync-teams / sync-matches for one of
    its competitions) when that family is skipped. Market, Kalshi and seed
    steps always run."""
    if not skip or st[0] not in SKIPPABLE or "--competition" not in st:
        return False
    return sports.get(st[st.index("--competition") + 1]) in skip


def plan(ref: dict) -> list[list[str]]:
    steps = [["init-db"], [SEED]]
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


EXPLAIN_FIELDS = ("id", "competition_id", "season", "status", "status_raw", "stage",
                  "utc_date", "external_ids")


def explain(db: Path, comp: str, season: str) -> dict:
    """Receipt for one competition-season (request 2026-09-27): the exact
    counting predicate, the same rows counted four ways, and every row's
    identity and status fields, each flagged counted or not. Read-only.
    Columns are taken from PRAGMA table_info: status_raw exists only where
    migrate_status_raw.py has run, so it is never assumed."""
    con = c.ro_connect(db)
    try:
        have = {r[1] for r in con.execute("PRAGMA table_info(matches)")}
        fields = [f for f in EXPLAIN_FIELDS if f in have]
        comps = [dict(zip(("id", "sport", "code", "name"), r)) for r in con.execute(
            "SELECT id, sport, code, name FROM competitions WHERE code = ? ORDER BY id", (comp,))]
        ids = [x["id"] for x in comps] or [-1]
        q = ",".join("?" * len(ids))
        prefix = season[:4] + "%"
        fp_rows = [dict(zip(("sport", "comp", "season", "status", "n"), r))
                   for r in con.execute(FINGERPRINT_SQL)
                   if r[1] == comp and r[2] == season]
        raw_exact = con.execute(f"SELECT COUNT(*) FROM matches WHERE competition_id IN ({q}) "
                                f"AND season = ?", [*ids, season]).fetchone()[0]
        by_season = {r[0]: r[1] for r in con.execute(
            f"SELECT season, COUNT(*) FROM matches WHERE competition_id IN ({q}) "
            f"AND season LIKE ? GROUP BY season", [*ids, prefix])}

        def group(col):
            if col not in have:
                return None
            return {str(r[0]): r[1] for r in con.execute(
                f"SELECT {col}, COUNT(*) FROM matches WHERE competition_id IN ({q}) "
                f"AND season = ? GROUP BY {col}", [*ids, season])}
        rows = []
        for r in con.execute(
                f"SELECT {', '.join('m.' + f for f in fields)}, c.code FROM matches m "
                f"LEFT JOIN competitions c ON c.id = m.competition_id "
                f"WHERE m.competition_id IN ({q}) AND m.season LIKE ? ORDER BY m.utc_date, m.id",
                [*ids, prefix]):
            row = dict(zip(fields + ["code"], r))
            row["counted"] = row["code"] == comp and row["season"] == season
            rows.append(row)
        groups = {k: group(k) for k in ("status", "status_raw", "stage")}
    finally:
        con.close()
    return {"producer": producer_version(), "host": c.host_name(), "comp": comp, "season": season,
            "predicate": FINGERPRINT_SQL, "competitions": comps,
            "fingerprint_count": sum(x["n"] for x in fp_rows), "fingerprint_rows": fp_rows,
            "raw_count_exact_season": raw_exact, "raw_count_by_season_string": by_season,
            "by_status": groups["status"], "by_status_raw": groups["status_raw"],
            "by_stage": groups["stage"], "fields_present": fields, "rows": rows}


def _ext_key(row: dict) -> str:
    ext = row.get("external_ids")
    try:
        ext = json.loads(ext) if isinstance(ext, str) else (ext or {})
    except ValueError:
        return str(ext)
    return json.dumps(sorted(ext.items()))


def explain_diff(lap: dict, host: dict) -> list[str]:
    """Join two explain dumps on external_ids; print every field difference."""
    L = {_ext_key(r): r for r in lap["rows"]}
    H = {_ext_key(r): r for r in host["rows"]}
    out = [f"laptop: {len(L)} rows (fingerprint counts {lap['fingerprint_count']}, raw "
           f"{lap['raw_count_exact_season']})  host: {len(H)} rows (fingerprint counts "
           f"{host['fingerprint_count']}, raw {host['raw_count_exact_season']})"]
    for side, a, b in (("laptop-only", L, H), ("host-only", H, L)):
        for k in sorted(set(a) - set(b)):
            r = a[k]
            out.append(f"  {side}: {k} season={r.get('season')!r} status={r.get('status')!r} "
                       f"status_raw={r.get('status_raw')!r} stage={r.get('stage')!r}")
    for k in sorted(set(L) & set(H)):
        diffs = [f"{f}: {L[k].get(f)!r} -> {H[k].get(f)!r}"
                 for f in ("code", "season", "status", "status_raw", "stage", "counted")
                 if L[k].get(f) != H[k].get(f)]
        if diffs:
            out.append(f"  differs {k}: " + "; ".join(diffs))
    return out


def parse_waiver(s: str) -> tuple[tuple[str, str], str]:
    """COMP:SEASON:reason. Seasons may contain '/', and reasons may contain ':'."""
    parts = s.split(":", 2)
    if len(parts) != 3 or not all(p.strip() for p in parts):
        raise SystemExit(f"✗ --waive expects COMP:SEASON:reason, got {s!r}")
    return (parts[0].strip(), parts[1].strip()), parts[2].strip()


def compare(lap: dict, host: dict, skip: set = frozenset(),
            waivers: dict | None = None) -> tuple[bool, list[str]]:
    waivers = dict(waivers or {})
    used: set = set()
    lines, ok = [], True
    sports = {**comp_sport(host), **comp_sport(lap)}

    def idx(fp):
        d: dict = {}
        for g in fp["games"]:
            s = d.setdefault((g["comp"], g["season"]), {})
            s[g["status"]] = s.get(g["status"], 0) + g["n"]  # sum, never overwrite
        return d
    L, H = idx(lap), idx(host)
    newest = newest_season(lap)
    for key in sorted(L):
        lt, ht = sum(L[key].values()), sum(H.get(key, {}).values())
        if sports.get(key[0]) in skip:
            lines.append(f"· {key[0]:5s} {key[1]:8s} N/A-host ({SKIP_TAG}: laptop-only family; "
                         f"laptop {lt} games)")
            continue
        lf, hf = L[key].get("FINISHED", 0), H.get(key, {}).get("FINISHED", 0)
        completed = key[1] != newest[key[0]]
        good = (lt == ht and lf == hf) if completed else True
        if not good and key in waivers:
            used.add(key)
            lines.append(f"~ {key[0]:5s} {key[1]:8s} total {lt:>6} vs {ht:>6}  FINISHED {lf:>6} vs "
                         f"{hf:>6}  WAIVED: {waivers[key]}")
            continue
        ok &= good
        tag = ("✓" if good else "✗") if completed else "·"
        lines.append(f"{tag} {key[0]:5s} {key[1]:8s} total {lt:>6} vs {ht:>6}  FINISHED {lf:>6} vs {hf:>6}"
                     + ("" if completed else "  (current season, informational)"))
    for key in sorted(set(waivers) - used):
        lines.append(f"· waiver unused {key[0]}:{key[1]} (row matched or absent): {waivers[key]}")
    for key in sorted(set(H) - set(L)):
        lines.append(f"· {key[0]:5s} {key[1]:8s} host-only ({sum(H[key].values())} games)")

    for a in ANCHORS:
        fam = a.get("sport") or sports.get(a.get("comp"))
        if fam in skip:
            lines.append(f"· ANCHOR {a['label']}: N/A-host ({SKIP_TAG})")
            continue
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

    lm = {_mkey(r): r for r in lap.get("model_registry", [])}
    hm = {_mkey(r): r for r in host.get("model_registry", [])}
    if not lm:
        ok = False
        lines.append("✗ MODEL laptop reference carries no production model rows")
    for k in sorted(set(lm) | set(hm)):
        a, b = lm.get(k), hm.get(k)
        good = bool(a and b and a["version"] == b["version"]
                    and a["_params_sha256"] == b["_params_sha256"])
        ok &= good
        lines.append(f"{'✓' if good else '✗'} MODEL {k[0]}/{k[1]}: laptop "
                     f"{a and a['version']} vs host {b and b['version']}  params "
                     f"{'match' if good else 'DIFFER/MISSING'}")
    return ok, lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="H1a fresh bootstrap + acceptance fingerprints.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fingerprint")
    f.add_argument("--out", type=Path, required=True)
    skip_help = f"skip a family's sync-teams/sync-matches ({SKIP_TAG}); e.g. MLB"
    for name in ("plan", "run"):
        p = sub.add_parser(name)
        p.add_argument("--reference", type=Path, required=True)
        p.add_argument("--skip-family", action="append", default=[], type=str.upper,
                       choices=FAMILY_ORDER, help=skip_help)
        if name == "run":
            p.add_argument("--from", dest="start", type=int, default=1)
    ex = sub.add_parser("explain", help="receipt for one competition-season (read-only)")
    ex.add_argument("--comp", required=True)
    ex.add_argument("--season", required=True)
    ex.add_argument("--out", type=Path, required=True)
    exd = sub.add_parser("explain-diff", help="join laptop and host explain dumps")
    exd.add_argument("laptop", type=Path)
    exd.add_argument("host", type=Path)
    cmp = sub.add_parser("compare")
    cmp.add_argument("laptop", type=Path)
    cmp.add_argument("host", type=Path)
    cmp.add_argument("--skip-family", action="append", default=[], type=str.upper,
                     choices=FAMILY_ORDER, help="report the family as N/A-host, not a failure")
    cmp.add_argument("--waive", action="append", default=[], metavar="COMP:SEASON:reason",
                     help="explained provider difference; the row still prints, marked WAIVED")
    a = ap.parse_args(argv)
    skip = set(getattr(a, "skip_family", []) or [])
    c.load_host_env()

    if a.cmd == "fingerprint":
        c.refuse_under_data(a.out.parent)
        fp = fingerprint(c.db_path())
        a.out.write_text(json.dumps(fp, indent=1))
        tot = sum(g["n"] for g in fp["games"])
        print(f"  producer: bootstrap.py blob {fp['producer']['bootstrap_blob_sha'][:12]} @ "
              f"{fp['producer']['git_commit']}")
        print(f"✓ fingerprint {a.out}: {tot} games, {len({(g['comp'], g['season']) for g in fp['games']})} "
              f"competition-seasons, odds_snapshots {fp['odds_snapshots_by_source']}, production "
              f"models {[r['version'] + ' ' + str(r['model_family']) for r in fp['model_registry']]}")
        return 0
    if a.cmd == "explain":
        c.refuse_under_data(a.out.parent)
        e = explain(c.db_path(), a.comp, a.season)
        a.out.write_text(json.dumps(e, indent=1, default=str))
        print(f"(a) counting predicate:\n    {e['predicate']}")
        print(f"    fields present in matches: {e['fields_present']}")
        print(f"competitions with code {a.comp!r}: {e['competitions']}")
        print(f"counts for {a.comp} {a.season}: fingerprint {e['fingerprint_count']}  "
              f"raw(season exact) {e['raw_count_exact_season']}  "
              f"raw by season string {e['raw_count_by_season_string']}")
        print(f"  by status {e['by_status']}\n  by status_raw {e['by_status_raw']}\n"
              f"  by stage {e['by_stage']}")
        excluded = [r for r in e["rows"] if not r["counted"]]
        print(f"(b) rows NOT counted by the fingerprint for {a.comp} {a.season}: {len(excluded)}")
        for r in excluded:
            print(f"    {r}")
        print(f"✓ explain written to {a.out} ({len(e['rows'])} rows); run explain-diff "
              f"laptop.json host.json for (c)")
        return 0
    if a.cmd == "explain-diff":
        print("\n".join(explain_diff(json.loads(a.laptop.read_text()),
                                      json.loads(a.host.read_text()))))
        return 0
    if a.cmd == "compare":
        waivers = dict(parse_waiver(w) for w in a.waive)
        lap_fp, host_fp = json.loads(a.laptop.read_text()), json.loads(a.host.read_text())
        refusal = version_mismatch(lap_fp, host_fp)
        if refusal:
            print(refusal)
            c.append_receipt({"kind": "bootstrap", "step": "compare", "exit": 2,
                              "refused": "version_mismatch",
                              "laptop_producer": lap_fp.get("producer"),
                              "host_producer": host_fp.get("producer")})
            return 2
        ok, lines = compare(lap_fp, host_fp, skip, waivers)
        print("\n".join(lines))
        print(f"\n{'PASS' if ok else 'FAIL'} — H1a phase-1 acceptance (completed seasons exact + anchors)")
        c.append_receipt({"kind": "bootstrap", "step": "compare", "exit": 0 if ok else 1,
                          "skipped_families": sorted(skip),
                          "waivers": [{"comp": k[0], "season": k[1], "reason": r,
                                       "applied": any(x.startswith(f"~ {k[0]:5s} {k[1]:8s}")
                                                      for x in lines)}
                                      for k, r in sorted(waivers.items())],
                          "fails": [x for x in lines if x.startswith("✗")][:40]})
        return 0 if ok else 1

    ref = json.loads(a.reference.read_text())
    steps = plan(ref)
    sports = comp_sport(ref)
    if a.cmd == "plan":
        for i, st in enumerate(steps, 1):
            if st == [SEED]:
                print(f"{i:3d}. [seed] install {len(ref.get('model_registry', []))} production "
                      f"model_versions rows from the reference (config only)")
            else:
                tag = f"   [{SKIP_TAG}]" if is_skipped(st, sports, skip) else ""
                print(f"{i:3d}. python cli.py {' '.join(st)}{tag}")
        return 0

    import sp_run
    if c.db_path().exists() and a.start == 1:
        raise SystemExit(f"✗ {c.db_path()} already exists — bootstrap is for a FRESH host. "
                         f"Resume a partial run with --from N.")
    run_id = f"{c.utc_now().strftime('%Y%m%dT%H%M%SZ')}-bootstrap"
    ok = skipped = 0
    with c.db_lock():
        for i, st in enumerate(steps, 1):
            if i < a.start:
                continue
            if st == [SEED]:
                out = seed_models(c.db_path(), ref.get("model_registry", []))
                print(f"\n=== [bootstrap {i}/{len(steps)}] seed model registry: {out['seeded']}")
                c.append_receipt({"kind": "step", "unit": "bootstrap", "run_id": run_id, "step": i,
                                  "command": "seed-model-registry", "exit": 0, **out})
                ok += 1
                continue
            line = f"python cli.py {' '.join(st)}"
            if is_skipped(st, sports, skip):
                print(f"\n=== [bootstrap {i}/{len(steps)}] {line}   -> {SKIP_TAG}", flush=True)
                c.append_receipt({"kind": "step", "unit": "bootstrap", "run_id": run_id, "step": i,
                                  "command": line, "exit": None, "skipped": SKIP_TAG})
                skipped += 1
                continue
            print(f"\n=== [bootstrap {i}/{len(steps)}] {line}", flush=True)
            rc, tail, dur = sp_run.run_step(st, run_id)
            c.append_receipt({"kind": "step", "unit": "bootstrap", "run_id": run_id, "step": i,
                              "command": line, "exit": rc, "duration_s": round(dur, 1),
                              "tail": tail})
            if rc != 0:
                again = "".join(f" --skip-family {s}" for s in sorted(skip))
                print(f"\n✗ step {i} failed (exit {rc}). Fix, then resume: bootstrap.py run "
                      f"--reference {a.reference} --from {i}{again}")
                c.append_receipt({"kind": "chain", "unit": "bootstrap", "run_id": run_id,
                                  "exit": rc, "steps_ok": ok, "steps_total": len(steps)})
                return rc
            ok += 1
    c.append_receipt({"kind": "chain", "unit": "bootstrap", "run_id": run_id, "exit": 0,
                      "steps_ok": ok, "steps_skipped": skipped, "skipped_families": sorted(skip),
                      "steps_total": len(steps),
                      "counts": c.table_counts(c.db_path(), c.CHAIN_COUNT_TABLES)})
    print(f"\n✓ bootstrap: {ok} steps run, {skipped} {SKIP_TAG}. Next: fingerprint --out "
          f"fp_host.json, then compare" + ("".join(f" --skip-family {s}" for s in sorted(skip))) + ".")
    return 0


if __name__ == "__main__":
    sys.exit(main())
