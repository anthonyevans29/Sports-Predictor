"""
THE NHL LEADERS-ORDER RECEIPT (ARCHITECT 2026-11-01 13:15 ET, addendum 200 item 1; lane nhl, the 11-05 step; #105),
READ-ONLY.

THE RULING (ARCHITECT 2026-11-01 13:15 ET, addendum 200), item 1 verbatim:
"1. NHL, THE LEADERS-ORDER READER (lane nhl, the 11-05 step, owner code; #105; the 10-30 ruling's item (1) made a
script). Build today, read-only: scripts/nhl_leaders_order_receipt.py, taking one or more payload directories as
arguments (the probe's --save dirs: <game id>_<endpoint>_<label>.json, labels T-120 .. T-0 and T+20). Per directory,
per game, per side: the landing page's matchup.goalieComparison <side>Team.leaders[0] at EVERY pregame poll (T-120,
T-90, T-60, T-45, T-35, T-30, T-15, T-0), printed in poll order so a flip shows; against the eventual starter, read
from the T+20 boxscore as nhl_goalies' boxscore ingest reads a goalie block (law 1: the saved files' real paths, not a
memory of them): the side's goalie with toi above zero. Two with toi above zero by T+20 is "two in net", counted and
never chosen; none, or no T+20 file, is "eventual starter unread". A missing landing file at a label, or a landing
with no goalieComparison or an empty leaders list, is "missing at <label>", counted. Per side the line ends AGREES /
DIFFERS / UNREAD at T-35 and at T-120, and the count of flips (leaders[0] changing between consecutive answered
pregame polls). The summary, per directory and across all of them: at T-35, agrees a of n (n = sides with a
leaders[0] at T-35 AND a read eventual starter); the same at T-120; missing at T-35; eventual unread; two in net;
sides with at least one flip; games read. Ids always, the payload's name beside the id where it carries one. No DB,
no network, nothing under data/, exit 0 on a complete read; tests on synthetic payload files in a tmp dir (a flip, a
miss, two in net, an unread eventual). The receipt text on #105 comes from MY host block on Monday (the payloads live
on the host; the script runs from /tmp with PYTHONPATH as #757's did), after the 11-01 unit has ended; your PR ships
no block. The hypothesis stays a hypothesis until I read it: nothing in the probe, the ingest or the registry changes
on this PR."

WHAT IT READS (the files scripts/nhl_starter_timing_probe.py --save writes, its own line:
`(save / f"{g['id']}_{r['endpoint']}_{label(o).split()[0]}.json")`, so the labels on disk are T-120, T-90, T-60,
T-45, T-35, T-30, T-15, T-0 and T+20):
  LEADERS   per pregame poll, the landing payload's matchup.goalieComparison.<side>Team.leaders[0]: its playerId, and
            its name beside it where the member carries one (name.default, else firstName + lastName, read with the
            ingest's own _text). "missing at <label>" when: no landing file at the label; the file does not parse;
            no matchup.goalieComparison object; no <side>Team.leaders list; an empty list; a leaders[0] with no
            integer playerId. Each is counted, with its reason printed; nothing is filled from another poll.
  EVENTUAL  the T+20 boxscore read by the ingest's OWN function, src.ingestion.nhl_goalies.boxscore_goalies (called,
            never copied: the goalie lists found by key, sided by a home/away path segment, each goalie's toi turned
            to seconds by the ingest's _toi_seconds, a goalie with no id dropped as the ingest drops it). Per side:
            exactly one goalie with toi_seconds above zero is the eventual starter; two or more is "two in net",
            counted and never chosen; none, no T+20 file, a file that does not parse, or a boxscore the ingest
            refuses (its goalie lists not sided as one home + one away) is "eventual starter unread", with the reason.
            Law 4: one goalie above zero beside a goalie whose toi the ingest could not read is also unread (that
            goalie may be a second in net), the reason printed: a reading for the architect to confirm (it moves n
            only on a boxscore with an unread toi). LIMITATION: a goalie the ingest drops for want of an id is
            invisible here, so an id-less second goalie in net is not seen (real NHL boxscores carry playerId).
  VERDICT   per side at T-35 and at T-120: AGREES (leaders[0] is the eventual starter) / DIFFERS / UNREAD (no
            leaders[0] at that poll, or no read eventual starter). FLIPS: leaders[0] changing between consecutive
            answered pregame polls (T-120 .. T-0; a missing poll is skipped, never a flip by itself).
  SUMMARY   per directory and across all: at T-35 agrees a of n (n = sides with a leaders[0] at T-35 AND a read
            eventual starter); the same at T-120; missing at T-35; eventual unread; two in net; sides with at least
            one flip; games read; missing by label; files that did not parse; files not of the probe's name form.

A directory named twice (or by two spellings of one path) is read once, the repeat printed and counted
(directories_given_twice). Ids always; the payload's name beside the id where it carries one (the game's away @ home abbrev from the first
payload that carries both; the goalie's name from its member). Standard library plus one repo import
(src.ingestion.nhl_goalies, whose module level imports only the standard library: no DB is opened, no network is
reached). Writes nothing. Exit 0 on a complete read (every directory read through; a file that does not parse is
counted and printed, never a stop); 2 refused: no directory given, a path that is not a directory, a directory under
data/, a directory holding no file of the probe's name form, or src.ingestion.nhl_goalies not importable (run from a
checkout, or with PYTHONPATH naming one). Last line `NHL-LEADERS-ORDER-RECEIPT {...}`.

Run:  python3 scripts/nhl_leaders_order_receipt.py DIR [DIR ...]
      PYTHONPATH=<checkout> python3 /tmp/nhl_leaders_order_receipt.py DIR [DIR ...]
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

_FILE = globals().get("__file__")
# run as a file inside a checkout: the checkout above scripts/; run as a copy elsewhere (/tmp, with PYTHONPATH naming
# the checkout) or from stdin: the working directory, which PYTHONPATH then backs
_HERE = Path(_FILE).resolve() if _FILE and Path(_FILE).is_file() else None
ROOT = _HERE.parents[1] if _HERE is not None and (_HERE.parents[1] / "src").is_dir() else Path.cwd()
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))                         # after PYTHONPATH: a named checkout wins

TAG = "NHL-LEADERS-ORDER-RECEIPT"
PREGAME = ("T-120", "T-90", "T-60", "T-45", "T-35", "T-30", "T-15", "T-0")
EVENTUAL = "T+20"
READ_AT = ("T-35", "T-120")                            # the ruled verdict polls, T-35 (the cutoff) first
SIDES = ("away", "home")
FNAME = re.compile(r"^(\d+)_(boxscore|landing|right-rail)_(T[-+]\d+)\.json$")
KNOWN_LABELS = (*PREGAME, EVENTUAL)


class Refused(Exception):
    pass


def _ingest():
    """The ingest module (its boxscore_goalies and _text), or Refused: the reading is the ingest's, never a copy."""
    try:
        from src.ingestion import nhl_goalies
    except Exception as e:                             # noqa: BLE001  (any import failure: refused, said why)
        raise Refused(f"src.ingestion.nhl_goalies not importable ({type(e).__name__}: {e}): run from a checkout, "
                      "or with PYTHONPATH naming one") from e
    return nhl_goalies


def _load(p: Path):
    """(payload, None) or (None, why)."""
    try:
        return json.loads(p.read_text(encoding="utf-8")), None
    except (OSError, ValueError) as e:
        return None, f"unreadable ({type(e).__name__})"


def _under_data(p: Path) -> bool:
    return "data" in p.resolve().parts


def scan(d: Path) -> dict:
    """{(game id, endpoint, label): path} for the files of the probe's name form, and the names skipped."""
    files, skipped = {}, []
    for f in sorted(d.iterdir()):
        m = FNAME.match(f.name) if f.is_file() else None
        if m and m.group(3) in KNOWN_LABELS:
            files[(int(m.group(1)), m.group(2), m.group(3))] = f
        elif f.is_file():
            skipped.append(f.name)
    return {"files": files, "skipped": skipped}


def _name(ng, member: dict) -> str | None:
    """The name a payload member carries: name.default (or a plain name), else firstName + lastName; the ingest's
    own _text reads each localized field."""
    n = ng._text(member.get("name"))
    if n:
        return n
    parts = [ng._text(member.get(k)) for k in ("firstName", "lastName")]
    return " ".join(p for p in parts if p) or None


def leader0(ng, landing, side: str) -> tuple[tuple[int, str | None] | None, str]:
    """((playerId, name) of leaders[0], "") or (None, why it is missing)."""
    if not isinstance(landing, dict):
        return None, "not an object"
    matchup = landing.get("matchup")
    gc = matchup.get("goalieComparison") if isinstance(matchup, dict) else None
    if not isinstance(gc, dict):
        return None, "no matchup.goalieComparison"
    team = gc.get(f"{side}Team")
    ls = team.get("leaders") if isinstance(team, dict) else None
    if not isinstance(ls, list):
        return None, f"no goalieComparison.{side}Team.leaders list"
    if not ls:
        return None, "empty leaders list"
    first = ls[0]
    pid = first.get("playerId") if isinstance(first, dict) else None
    if not isinstance(pid, int) or isinstance(pid, bool):
        return None, "leaders[0] carries no playerId"
    return (pid, _name(ng, first)), ""


def _who(pid: int, name: str | None) -> str:
    return f"{pid} ({name})" if name else str(pid)


def eventual(ng, box) -> dict:
    """Per side: {"state": "read"|"two in net"|"unread", "id", "name", "why", "on": [(id, name, toi)]}, read by the
    ingest's boxscore_goalies (its sided lists, its toi_seconds)."""
    if box is None:
        return {s: {"state": "unread", "why": "no T+20 boxscore file"} for s in SIDES}
    rows, receipt = ng.boxscore_goalies(box)
    if rows is None:
        lists = ", ".join(receipt.get("goalie_lists") or []) or "none"
        return {s: {"state": "unread", "why": f"the ingest refused the boxscore: goalie lists not sided one home + "
                                              f"one away (lists: {lists})"} for s in SIDES}
    out = {}
    for side in SIDES:
        mine = [r for r in rows if r["side"] == side]
        on = [(r["goalie_id"], r["goalie_name"], r["toi_seconds"]) for r in mine
              if r["toi_seconds"] is not None and r["toi_seconds"] > 0]
        toi_unread = [_who(r["goalie_id"], r["goalie_name"]) for r in mine if r["toi_seconds"] is None]
        if len(on) >= 2:
            out[side] = {"state": "two in net", "on": on,
                         "why": f"{len(on)} goalies with toi above zero: "
                                + ", ".join(f"{_who(i, n)} {t}s" for i, n, t in on)}
        elif len(on) == 1 and not toi_unread:
            out[side] = {"state": "read", "id": on[0][0], "name": on[0][1], "on": on, "why": ""}
        elif len(on) == 1:
            out[side] = {"state": "unread", "on": on,
                         "why": f"one goalie with toi above zero, {_who(*on[0][:2])}, beside toi unread on "
                                f"{', '.join(toi_unread)}"}
        else:
            out[side] = {"state": "unread", "on": [],
                         "why": ("no goalie listed" if not mine else "no goalie with toi above zero")
                                + (f"; toi unread on {', '.join(toi_unread)}" if toi_unread else "")}
    return out


def _game_name(files: dict, gid: int) -> str | None:
    """'AWAY @ HOME' from the first payload (landing polls in order, then the T+20 boxscore) carrying both abbrevs."""
    order = [(gid, "landing", p) for p in PREGAME] + [(gid, "boxscore", EVENTUAL)]
    for k in order:
        if k not in files:
            continue
        p, _ = _load(files[k])
        if isinstance(p, dict):
            a, h = p.get("awayTeam"), p.get("homeTeam")
            aa = a.get("abbrev") if isinstance(a, dict) else None
            ha = h.get("abbrev") if isinstance(h, dict) else None
            if isinstance(aa, str) and isinstance(ha, str):
                return f"{aa} @ {ha}"
    return None


def read_game(ng, files: dict, gid: int) -> dict:
    landings = {}
    unreadable = []
    for p in PREGAME:
        f = files.get((gid, "landing", p))
        if f is None:
            landings[p] = (None, "no landing file")
            continue
        payload, why = _load(f)
        if why:
            unreadable.append(f.name)
        landings[p] = (payload, why)
    box, box_why = None, "no T+20 boxscore file"
    bf = files.get((gid, "boxscore", EVENTUAL))
    if bf is not None:
        box, box_why = _load(bf)
        if box_why:
            unreadable.append(bf.name)
    ev = eventual(ng, box)
    if bf is not None and box_why:
        ev = {s: {"state": "unread", "why": f"T+20 boxscore {box_why}"} for s in SIDES}
    sides = {}
    for side in SIDES:
        polls = {}
        for p in PREGAME:
            payload, why = landings[p]
            polls[p] = (None, why) if why else leader0(ng, payload, side)
        answered = [(p, polls[p][0]) for p in PREGAME if polls[p][0] is not None]
        flips = [(a[0], b[0], a[1], b[1]) for a, b in zip(answered, answered[1:]) if a[1][0] != b[1][0]]
        e = ev[side]
        verdict = {}
        for p in READ_AT:
            l0 = polls[p][0]
            if l0 is None or e["state"] != "read":
                verdict[p] = "UNREAD"
            else:
                verdict[p] = "AGREES" if l0[0] == e["id"] else "DIFFERS"
        sides[side] = {"polls": polls, "flips": flips, "eventual": e, "verdict": verdict}
    return {"id": gid, "name": _game_name(files, gid), "sides": sides, "unreadable": unreadable}


def side_line(side: str, s: dict) -> str:
    parts = []
    for p in PREGAME:
        l0, why = s["polls"][p]
        parts.append(f"{p} {_who(*l0)}" if l0 else f"missing at {p} ({why})")
    e = s["eventual"]
    ev = (f"eventual {_who(e['id'], e.get('name'))}" if e["state"] == "read"
          else f"eventual: two in net ({e['why']})" if e["state"] == "two in net"
          else f"eventual starter unread ({e['why']})")
    fl = "; ".join(f"{a}->{b} {_who(*x)}->{_who(*y)}" for a, b, x, y in s["flips"])
    return (f"    {side}: " + " · ".join(parts) + f" · {ev} · "
            + " · ".join(f"{p} {s['verdict'][p]}" for p in READ_AT)
            + f" · flips {len(s['flips'])}" + (f" ({fl})" if fl else ""))


def tally(games: list[dict], skipped: int) -> Counter:
    t = Counter()
    t["games read"] = len(games)
    t["files not of the name form"] = skipped
    for g in games:
        t["files that did not parse"] += len(g["unreadable"])
        for s in g["sides"].values():
            t["sides"] += 1
            for p in READ_AT:
                if s["verdict"][p] != "UNREAD":
                    t[f"n at {p}"] += 1
                    t[f"agrees at {p}"] += s["verdict"][p] == "AGREES"
                    t[f"differs at {p}"] += s["verdict"][p] == "DIFFERS"
            for p in PREGAME:
                if s["polls"][p][0] is None:
                    t[f"missing at {p}"] += 1
            st = s["eventual"]["state"]
            t["eventual unread"] += st == "unread"
            t["two in net"] += st == "two in net"
            t["sides with at least one flip"] += bool(s["flips"])
    return t


def summary_line(head: str, t: Counter) -> str:
    def rate(p):
        n = t[f"n at {p}"]
        return f"at {p}: agrees {t[f'agrees at {p}']} of {n}" + (f" ({t[f'agrees at {p}'] / n:.0%})" if n else "")
    return (f"  {head}: {rate('T-35')} · {rate('T-120')} · missing at T-35 {t['missing at T-35']} · "
            f"eventual unread {t['eventual unread']} · two in net {t['two in net']} · "
            f"sides with at least one flip {t['sides with at least one flip']} · games read {t['games read']} · "
            f"sides {t['sides']} · missing by label "
            + ", ".join(f"{p} {t[f'missing at {p}']}" for p in PREGAME)
            + f" · files that did not parse {t['files that did not parse']} · "
              f"files not of the name form {t['files not of the name form']}")


def _as_dict(t: Counter) -> dict:
    keys = ["games read", "sides", *(f"{k} at {p}" for p in READ_AT for k in ("agrees", "differs", "n")),
            "missing at T-35", "eventual unread", "two in net", "sides with at least one flip",
            *(f"missing at {p}" for p in PREGAME), "files that did not parse", "files not of the name form"]
    return {k.replace(" ", "_"): t[k] for k in dict.fromkeys(keys)}


def main(argv=None, out=print) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        out("refused: no payload directory given · Run:  python3 scripts/nhl_leaders_order_receipt.py DIR [DIR ...]")
        return 2
    dirs, repeats, seen = [], [], set()
    for a in args:
        d = Path(a).expanduser()
        if d.resolve() in seen:
            repeats.append(a)
            continue
        seen.add(d.resolve())
        dirs.append(d)
    try:
        for d in dirs:
            if _under_data(d):
                raise Refused(f"{d}: under data/, never read")
            if not d.is_dir():
                raise Refused(f"{d}: not a directory")
        ng = _ingest()
        scans = [scan(d) for d in dirs]
        for d, sc in zip(dirs, scans):
            if not sc["files"]:
                raise Refused(f"{d}: no file of the probe's name form (<game id>_<endpoint>_<label>.json)")
    except Refused as e:
        out(f"refused: {e}")
        return 2
    out("NHL LEADERS-ORDER RECEIPT (ARCHITECT 2026-11-01 13:15 ET, addendum 200 item 1; #105) · read-only · no DB, "
        "no network · the hypothesis \"leaders[0] at T-35 is the projected starter\" read, never assumed")
    out("  leaders[0]: landing matchup.goalieComparison.<side>Team.leaders[0] at " + ", ".join(PREGAME)
        + f" · eventual: the {EVENTUAL} boxscore through src.ingestion.nhl_goalies.boxscore_goalies, the side's "
          "goalie with toi above zero · ids always, the payload's name beside where it carries one")
    if repeats:
        out(f"  {len(repeats)} argument(s) naming a directory already given, read once: " + ", ".join(repeats))
    every = []
    total = Counter()
    for d, sc in zip(dirs, scans):
        files = sc["files"]
        gids = sorted({k[0] for k in files})
        out(f"DIR {d.resolve()} · {len(files)} payload file(s) · {len(gids)} game(s)"
            + (f" · {len(sc['skipped'])} file(s) not of the probe's name form, not read: "
               + ", ".join(sc["skipped"][:10]) + (" ..." if len(sc["skipped"]) > 10 else "") if sc["skipped"] else ""))
        games = [read_game(ng, files, g) for g in gids]
        for g in games:
            out(f"  GAME {g['id']}" + (f" ({g['name']})" if g["name"] else "")
                + (f" · did not parse: {', '.join(g['unreadable'])}" if g["unreadable"] else ""))
            for side in SIDES:
                out(side_line(side, g["sides"][side]))
        t = tally(games, len(sc["skipped"]))
        out(summary_line(f"SUMMARY {d.resolve()}", t))
        total += t
        every += [g["id"] for g in games]
    distinct = len(set(every))
    out(summary_line(f"SUMMARY ALL ({len(dirs)} director{'y' if len(dirs) == 1 else 'ies'}"
                     + (f"; {distinct} distinct game id(s)" if distinct != len(every) else "") + ")", total))
    out(f"{TAG} " + json.dumps({"directories": len(dirs), "directories_given_twice": len(repeats),
                                "distinct_game_ids": distinct, **_as_dict(total)},
                               sort_keys=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
