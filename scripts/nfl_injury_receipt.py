"""
NFL INJURY-READ RECEIPT (#627; ARCHITECT 2026-10-23, addendum 162 item 3(c): "#627's receipt (raw entries vs retained,
join failures, observation time, per closing) is due with the packet") — read-only. The finding, verbatim (addendum
146 item 1(vii)): "the provider returning an empty list for 3 of 16 teams at T-35 is a data gap: the Issue counts, per
closing, the teams with an empty list, and says whether the feed or our read is empty. No rule change."

WHAT IS STORED (law 1: read 2026-10-27). The injuries table is replace-on-sync (one team's rows deleted and rewritten
each read), so a past read's raw answer is not kept. What a closing keeps of it:
  - its closing file (<exports>/closing_NFL_<start>.json, redated.closing_rows' glob): each row's
    input_quality.injuries.<home|away> = {count (rows retained), qb_listed, positions_unresolved (the roster join's
    failures), synced_at (the newest refreshed_at of the team's rows: the observation time)} (nfl_predict.py);
  - its closing receipt (sp_common.receipts_path(), kind "closing", joined by run_id): the sync-injuries step's
    empty_answers, the teams whose provider answer held NO entry (cli.py's EMPTY-ANSWER line; closing.empty_answers).

So per closing, a team with count 0 is either the FEED (the receipt names it: the provider answered empty) or OUR READ
(the provider answered, and nothing was retained), or UNKNOWN (no receipt for the run). The raw entry count of a past
read is not recoverable; --live reads it now.

Sections:
  C  per closing        each NFL closing file (--since, default 2026-10-11): the run's start and run_id; the teams;
                        the teams with count 0, each FEED / OUR READ / UNKNOWN; the join failures (positions
                        unresolved, per team); the observation age (the page's start minus synced_at) per team: the
                        median and the largest, and the teams with no synced_at.
  T  the totals         over the closings: team-readings, empty ones by cause, join failures, ages.
  L  --live             one provider read per NFL team now (/teams?league&season, then per team /players?team&season
                        and /injuries?team), through the adapter's own helpers (qb_audit.injury_entries,
                        roster_index, resolve_position): raw entries in the answer, the entries the read takes (one per
                        provider id), the entries the sync retains (a name), and the positions the roster join leaves
                        unresolved (the position lookup is NOT asked: nothing is written). Payloads kept in --save.

Run:  python3 scripts/nfl_injury_receipt.py [--exports DIR] [--receipts PATH] [--since YYYY-MM-DD]
                                            [--live [--save DIR] [--season 2026]]
Opens no database; writes nothing but --live's kept payloads (refused under data/). Paste the output to the architect.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))

FAMILY = "NFL"
DEFAULT_SINCE = "2026-10-11"                 # the first closings after addendum 40 item 4's empty-answer line
DEFAULT_SAVE = ROOT / "logs" / "nfl_injury_payloads"


def _utc(v) -> datetime | None:
    """A stored stamp as naive UTC (the code's convention); None when absent or unreadable."""
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d


def closings(exports: Path, since: datetime) -> list[dict]:
    """The NFL closing files, oldest first: {file, start, run_id, rows}."""
    out = []
    for p in sorted(exports.glob("closing_*.json")) if exports.is_dir() else []:
        try:
            doc = json.loads(p.read_text())
            block = doc.get("closing") or {}
        except (OSError, ValueError, AttributeError):
            out.append({"file": p.name, "unreadable": True})
            continue
        fam = block.get("family") or (p.name.split("_")[1] if p.name.count("_") >= 2 else None)
        if fam != FAMILY:
            continue
        start = _utc(block.get("start"))
        if start is not None and start < since:
            continue
        out.append({"file": p.name, "start": start, "run_id": block.get("run_id"),
                    "rows": [r for r in doc.get("predictions") or [] if isinstance(r, dict)]})
    return sorted(out, key=lambda c: (c.get("start") or datetime.min, c["file"]))


def receipts_by_run(path: Path) -> dict:
    """{run_id: the closing receipt's empty-answer teams (a set)}; a run with no sync-injuries step record maps to None."""
    out = {}
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return out
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if not isinstance(r, dict) or r.get("kind") != "closing" or not r.get("run_id"):
            continue
        steps = [s for s in r.get("steps") or [] if isinstance(s, dict)]
        inj = [s for s in steps if " sync-injuries" in f" {s.get('command') or ''}"]   # closing.py's step record
        empty = set(r.get("injury_lists_empty") or [])
        for s in inj:
            empty |= set(s.get("empty_answers") or [])
        prev = out.get(r["run_id"])
        out[r["run_id"]] = (prev or set()) | empty if (inj or r.get("injury_lists_empty") is not None) else prev
    return out


def read_closing(c: dict, receipts: dict) -> dict:
    sides, empty, join_fail, ages, no_stamp = {}, [], Counter(), [], []
    feed = receipts.get(c.get("run_id")) if c.get("run_id") else None
    known = c.get("run_id") in receipts
    for r in c["rows"]:
        inj = (r.get("input_quality") or {}).get("injuries") or {}
        for side, team in (("home", r.get("home_team")), ("away", r.get("away_team"))):
            b = inj.get(side)
            if not isinstance(b, dict) or team in sides:
                continue
            sides[team] = b
            if b.get("count") == 0:
                why = ("UNKNOWN (no receipt for the run)" if not known or feed is None else
                       "FEED (the provider answered no entry)" if team in feed else
                       "OUR READ (the provider answered; nothing retained)")
                empty.append((team, why))
            if b.get("positions_unresolved"):
                join_fail[team] = len(b["positions_unresolved"])
            st = _utc(b.get("synced_at"))
            if st is None:
                no_stamp.append(team)
            elif c.get("start"):
                ages.append(((c["start"] - st).total_seconds() / 60, team))
    return {"teams": len(sides), "empty": empty, "join_fail": join_fail, "ages": ages, "no_stamp": no_stamp,
            "receipt": known}


def closing_lines(c: dict, x: dict) -> list[str]:
    L = [f"  C {c['file']} · start {c['start']:%Y-%m-%d %H:%MZ} · run {c.get('run_id') or '(none)'} · teams "
         f"{x['teams']} · receipt {'read' if x['receipt'] else 'NOT FOUND'}"]
    L.append("      empty lists (count 0): " + ("; ".join(f"{t}: {w}" for t, w in x["empty"]) or "none"))
    L.append("      join failures (positions unresolved): " + (" · ".join(f"{t} {n}" for t, n in
                                                                     sorted(x["join_fail"].items())) or "none"))
    if x["ages"]:
        a = sorted(m for m, _ in x["ages"])
        worst = max(x["ages"])
        L.append(f"      observation age (start - synced_at): median {statistics.median(a):.0f} min · largest "
                 f"{worst[0]:.0f} min ({worst[1]})" + (f" · no synced_at: {', '.join(x['no_stamp'])}"
                                                      if x["no_stamp"] else ""))
    else:
        L.append("      observation age: no synced_at on any team" if x["no_stamp"] else "      observation age: none")
    return L


def live(save: Path, season: int, get=None) -> list[str]:
    """One provider read per NFL team now (see the module doc); the position lookup is not asked."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("nfl_qb_probe", ROOT / "scripts" / "nfl_qb_probe.py")
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    from src.walters.qb_audit import injury_entries, resolve_position, roster_index
    get = get or probe.get

    def keep(name, rows):
        save.mkdir(parents=True, exist_ok=True)
        (save / f"{name}.json").write_text(json.dumps(rows, sort_keys=True, default=str))

    code, errs, teams = get("teams", league=probe.LEAGUE, season=season)
    keep(f"teams_{season}", teams)
    L = [f"  L live read, season {season}: /teams answered {len(teams)} team(s) (HTTP {code}{', errors ' + str(errs) if errs else ''})"]
    tot = Counter()
    for t in sorted((x for x in teams if isinstance(x, dict) and x.get("id") is not None), key=lambda x: str(x["id"])):
        tid, name = t["id"], t.get("name")
        _, rerrs, roster = get("players", team=tid, season=season)
        _, ierrs, items = get("injuries", team=tid)
        keep(f"roster_{tid}", roster)
        keep(f"injuries_{tid}", items)
        idx = roster_index(roster)
        entries = injury_entries([i for i in items if isinstance(i, dict) and isinstance(i.get("player"), dict)])
        named = [e for e in entries if (e[0]["player"].get("name") or "").strip()]
        unres = [e[0]["player"]["name"] for e in named if resolve_position(e[0]["player"], idx, by_name=e[1])[0] is None]
        tot.update(raw=len(items), taken=len(entries), retained=len(named), unresolved=len(unres),
                   empty=0 if items else 1, roster_empty=0 if roster else 1)
        L.append(f"      {tid} {name}: raw {len(items)} · taken {len(entries)} · retained {len(named)} · positions "
                 f"unresolved {len(unres)}" + (f" ({', '.join(unres)})" if unres else "") +
                 (" · roster EMPTY" if not roster else "") + (f" · errors {rerrs or ierrs}" if rerrs or ierrs else ""))
    L.append(f"    live totals: raw {tot['raw']} · taken {tot['taken']} · retained {tot['retained']} · positions "
             f"unresolved {tot['unresolved']} · teams answering empty {tot['empty']} · rosters empty "
             f"{tot['roster_empty']}")
    return L


def main(argv=None, echo=print, get=None) -> int:
    import sp_common as c
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--exports", default=str(ROOT / "exports"))
    ap.add_argument("--receipts", default=None, help="default: sp_common.receipts_path()")
    ap.add_argument("--since", default=DEFAULT_SINCE)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--save", default=str(DEFAULT_SAVE))
    ap.add_argument("--season", type=int, default=2026)
    a = ap.parse_args(argv)
    receipts_path = Path(a.receipts) if a.receipts else c.receipts_path()
    since = datetime.fromisoformat(a.since)
    cs = closings(Path(a.exports), since)
    rec = receipts_by_run(receipts_path)
    echo(f"NFL INJURY-READ RECEIPT (#627; addendum 162 item 3(c)) · read-only, opens no database · closings "
         f"{a.exports}/closing_*.json since {a.since} · receipts {receipts_path}")
    tot, ages, unreadable = Counter(), [], [x["file"] for x in cs if x.get("unreadable")]
    for cl in (x for x in cs if not x.get("unreadable")):
        x = read_closing(cl, rec)
        for ln in closing_lines(cl, x):
            echo(ln)
        tot["closings"] += 1
        tot["team readings"] += x["teams"]
        tot["join failures"] += sum(x["join_fail"].values())
        tot["no synced_at"] += len(x["no_stamp"])
        for _, why in x["empty"]:
            tot["empty: " + why.split(" ")[0]] += 1
        ages += [m for m, _ in x["ages"]]
    echo(f"  T totals: closings {tot['closings']} · team-readings {tot['team readings']} · empty lists FEED "
         f"{tot['empty: FEED']} · OUR READ {tot['empty: OUR']} · UNKNOWN {tot['empty: UNKNOWN']} · join failures "
         f"{tot['join failures']} · no synced_at {tot['no synced_at']}"
         + (f" · observation age median {statistics.median(ages):.0f} min, largest {max(ages):.0f} min" if ages
            else "") + (f" · unreadable files {', '.join(unreadable)}" if unreadable else ""))
    if a.live:
        save = Path(a.save).expanduser().resolve()
        if (ROOT / "data").resolve() in (save, *save.parents):
            raise SystemExit(f"REFUSED: --save {save} is under data/ (law 5)")
        for ln in live(save, a.season, get=get):
            echo(ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
