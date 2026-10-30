"""
NHL LEADERS-ORDER READ (ARCHITECT 2026-10-30 08:10 ET, candidate nine, #105, item (1)) — read-only, no network.

Verbatim: "HYPOTHESIS to test, never assumed: leaders[0] at T-35 is the projected starter. (1) Today, read-only from
logs/nhl_probe_payloads_2026-10-28/: per side of the four games, leaders[0] at each poll T-120..T-15 against the goalie
with toi > 0 in the T+20 boxscore; print the order at every poll (does it flip as the start nears?)."

Reads the payloads scripts/nhl_starter_timing_probe.py --save keeps (<game id>_<endpoint>_<label>.json; label T-120,
T-90, T-60, T-45, T-35, T-30, T-15, T-0, T+20). Standard library only, so it runs on any checkout. It writes nothing.

  SHAPE   once per directory: every path in a landing payload whose segments name "goalie", with its value's type and
          (for a list) its length and first member's keys; the same for right-rail. Law 1: the shape is printed
          before any reading rests on it.
  ORDER   per game and side, at every pregame poll T-120 .. T-15 (and T-0 where kept): the landing page's
          matchup.goalieComparison.<side>Team.leaders, in the payload's own order (playerId and name), leaders[0]
          marked. A poll whose payload is missing, or whose page holds no leaders list, prints so; nothing is filled.
  FLIPS   per side: how many times leaders[0] changes between consecutive kept polls, and where.
  EVENTUAL per side: the goalie(s) with toi > 0 in the T+20 boxscore (playerByGameStats.<side>Team.goalies). Exactly
          one: the eventual starter. None, or more than one (a goalie pulled before T+20): unread, never guessed. Read
          only to test the hypothesis, never to fill the pregame record.
  PROBE   the probe's own asserted() on the first game's T-35 landing payload (scripts/nhl_starter_timing_probe.py,
          when this checkout has it): the kind it classed per side, so "the probe missed listed" is read, not assumed.
  READ    per side: leaders[0] at T-35 against the eventual starter (agrees / differs / no T-35 leaders / eventual
          unread), and the same at T-120. Totals: n sides read at each poll, agrees, the hit rate. A hit rate is a
          count over these games only: the hypothesis is tested, never assumed (the 11-05 receipt adds the next days).

Run:  python3 scripts/nhl_leaders_order_read.py DIR [DIR ...]
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

POLLS = ("T-120", "T-90", "T-60", "T-45", "T-35", "T-30", "T-15", "T-0")
PREGAME = POLLS[:-1]                                  # T-120 .. T-15, as ruled; T-0 printed, never counted
SIDES = ("away", "home")
FNAME = re.compile(r"^(\d+)_(boxscore|landing|right-rail)_(T[-+]\d+)\.json$")


def load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return {"__unreadable__": f"{type(e).__name__}: {e}"}


def walk(obj, path=""):
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        yield path, obj
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")


def shape_lines(payload, endpoint: str) -> list[str]:
    out = []
    for path, v in walk(payload):
        if not re.search(r"goalie", path, re.I) or re.search(r"\[\d+\]", path):
            continue                                   # a list member's own paths: its keys print with its list
        if isinstance(v, list):
            first = v[0] if v else None
            out.append(f"    {endpoint} {path}: list of {len(v)}"
                       + (f", first member keys {sorted(first)}" if isinstance(first, dict) else ""))
        elif isinstance(v, dict):
            out.append(f"    {endpoint} {path}: object, keys {sorted(v)}")
    return out or [f"    {endpoint}: no path naming 'goalie'"]


def _name(d: dict) -> str:
    n = d.get("name")
    if isinstance(n, dict):
        n = n.get("default")
    if not isinstance(n, str):
        parts = [d.get(k, {}).get("default") if isinstance(d.get(k), dict) else d.get(k)
                 for k in ("firstName", "lastName")]
        n = " ".join(p for p in parts if isinstance(p, str)) or None
    return n or "?"


def leaders(landing, side: str):
    """The side's matchup.goalieComparison leaders, in the payload's order: [(playerId, name)], or None (no list)."""
    gc = ((landing or {}).get("matchup") or {}).get("goalieComparison") if isinstance(landing, dict) else None
    team = (gc or {}).get(f"{side}Team") if isinstance(gc, dict) else None
    ls = team.get("leaders") if isinstance(team, dict) else None
    if not isinstance(ls, list):
        return None
    return [(d.get("playerId"), _name(d)) for d in ls if isinstance(d, dict)]


def _secs(toi) -> int | None:
    if isinstance(toi, str) and re.fullmatch(r"\d+:\d{2}", toi):
        m, s = toi.split(":")
        return int(m) * 60 + int(s)
    return None


def eventual(box, side: str):
    """(the one goalie with toi > 0, why): (id, name) and "" when exactly one, else None and the reason."""
    team = (((box or {}).get("playerByGameStats") or {}).get(f"{side}Team")) if isinstance(box, dict) else None
    gs = team.get("goalies") if isinstance(team, dict) else None
    if not isinstance(gs, list):
        return None, "no playerByGameStats goalies list"
    on = [(g.get("playerId"), _name(g), g.get("toi")) for g in gs if isinstance(g, dict) and (_secs(g.get("toi")) or 0) > 0]
    unread = [g.get("toi") for g in gs if isinstance(g, dict) and _secs(g.get("toi")) is None]
    if len(on) == 1:
        return on[0][:2], ""
    return None, (f"{len(on)} goalies with toi > 0 ({', '.join(f'{i} {n} {t}' for i, n, t in on)})" if on
                  else "no goalie with toi > 0") + (f"; toi unread on {len(unread)}" if unread else "")


def _probe():
    """The probe's own module from this checkout (its asserted() is what the probe classed), or None."""
    try:
        f = Path(globals().get("__file__") or "<stdin>")
        here = f.resolve().parent if f.is_file() else Path("scripts").resolve()   # read from stdin: the cwd's scripts/
        sys.path[:0] = [str(here.parent), str(here)]
        import nhl_starter_timing_probe as tp
        return tp
    except Exception:                                   # a checkout without it, or its imports: not read, said so
        return None


def main(argv) -> int:
    dirs = [Path(a) for a in argv]
    if not dirs:
        print(__doc__.strip().splitlines()[-1])
        return 2
    print("NHL LEADERS-ORDER READ (ARCHITECT 2026-10-30 08:10 ET, #105 item (1)) · read-only · the hypothesis "
          "\"leaders[0] at T-35 is the projected starter\" tested, never assumed")
    tally = {p: Counter() for p in POLLS}
    for d in dirs:
        files = {}
        skipped = []
        for f in sorted(d.glob("*.json")) if d.is_dir() else []:
            m = FNAME.match(f.name)
            if m:
                files[(int(m.group(1)), m.group(2), m.group(3))] = f
            else:
                skipped.append(f.name)
        games = sorted({k[0] for k in files})
        print(f"DIR {d} · {'not a directory' if not d.is_dir() else f'{len(files)} payload(s), {len(games)} game(s)'}"
              + (f" · {len(skipped)} file(s) not of the probe's name form" if skipped else ""))
        if not games:
            continue
        print("  SHAPE (law 1: what the pages hold under a 'goalie' path, read from the first kept poll of the first game):")
        g0 = games[0]
        for ep in ("landing", "right-rail"):
            f = next((files[(g0, ep, p)] for p in POLLS if (g0, ep, p) in files), None)
            print("\n".join(shape_lines(load(f), ep)) if f else f"    {ep}: no payload kept for {g0}")
        probe = _probe()
        f = next((files[(g0, "landing", p)] for p in ("T-35", *POLLS) if (g0, "landing", p) in files), None)
        if probe is None or f is None:
            print("  PROBE: " + ("scripts/nhl_starter_timing_probe.py not importable from this checkout"
                                 if probe is None else "no landing payload kept") + ": its own class not read")
        else:
            a = probe.asserted(load(f))
            print(f"  PROBE (the probe's own asserted() on {f.name}): "
                  + " · ".join(f"{sd} kind {a[sd]['kind']}, listed {a[sd]['listed']}, ids {a[sd]['ids']}" for sd in SIDES))
        for g in games:
            box = load(files[(g, "boxscore", "T+20")]) if (g, "boxscore", "T+20") in files else None
            for side in SIDES:
                ev, why = eventual(box, side) if box is not None else (None, "no T+20 boxscore kept")
                print(f"  {g} {side} · eventual (T+20 boxscore, toi > 0): " + (f"{ev[0]} {ev[1]}" if ev else f"unread ({why})"))
                firsts = []
                for p in POLLS:
                    f = files.get((g, "landing", p))
                    if f is None:
                        print(f"    {p}: no landing payload kept")
                        continue
                    ls = leaders(load(f), side)
                    if ls is None:
                        print(f"    {p}: no matchup.goalieComparison.{side}Team.leaders list")
                        continue
                    order = ", ".join(f"{'[0] ' if i == 0 else ''}{pid} {nm}" for i, (pid, nm) in enumerate(ls))
                    print(f"    {p}: leaders ({len(ls)}) {order or 'empty'}")
                    if ls:
                        firsts.append((p, ls[0][0]))
                        t = tally[p]
                        t["read"] += 1
                        if ev is None:
                            t["eventual unread"] += 1
                        elif ls[0][0] == ev[0]:
                            t["agrees"] += 1
                        else:
                            t["differs"] += 1
                flips = [f"{a[0]}->{b[0]} ({a[1]}->{b[1]})" for a, b in zip(firsts, firsts[1:]) if a[1] != b[1]]
                print(f"    flips of leaders[0] across the kept polls: {len(flips)}" + (f" · {'; '.join(flips)}" if flips else ""))
    print("READ (sides with a leaders list at the poll; agrees = leaders[0] is the eventual starter):")
    for p in POLLS:
        t = tally[p]
        judged = t["agrees"] + t["differs"]
        print(f"  {p}{' (the cutoff)' if p == 'T-35' else ''}{' (printed, not in the ruled range)' if p == 'T-0' else ''}: "
              f"read {t['read']} · agrees {t['agrees']} · differs {t['differs']} · eventual unread {t['eventual unread']}"
              + (f" · hit rate {t['agrees']}/{judged} ({t['agrees'] / judged:.0%})" if judged else " · hit rate: none judged"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
