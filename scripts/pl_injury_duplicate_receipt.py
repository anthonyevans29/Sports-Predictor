"""
THE PL INJURY DUPLICATE RECEIPT (ARCHITECT 2026-11-22 09:03 ET, addendum 446 item 1; Refs #1052), READ-ONLY.

THE ORDER (addendum 446 item 1), verbatim:
"1. ONE PLAYER LISTED TWICE IN A SIDE'S INJURY LIST. Chelsea's list on the slate and on the 15:00Z closing
   page holds seven names, and two pairs are one player each under two spellings: one name with and
   without its accent, and one double surname beside its short form (the names stay off the public
   record; they are on the page). The row's home_injuries_count reads 7 where five players are listed.
   That count is an input of v22's injury factor, so Chelsea was marked down for seven. The Desk's
   call was PASS (the pick under the probability floor), so no call rested on it.
   THE RECEIPT, read-only, on the host's pulled copy and the mirror's pages: for every Premier League
   closing row of 2026/27, each side's entries, its distinct players by the source's own player id,
   and the pairs that are the same person by name once accents and a double surname are folded; how
   many rows and sides carry such a pair; and whether the two entries of a pair carry two source ids
   or one. Counts and the rule you used. I rule on the receipt; nothing is de-duplicated before that."

WHAT IT ANSWERS: for every Premier League closing row of 2026/27, each side's entries, its distinct players by the
source's own player id, the pairs that are the same person by name once accents and a double surname are folded; how
many rows and sides carry such a pair; whether the two entries of a pair carry two source ids or one. Counts and the
rule used.

THE ROWS (--exports DIR, required): a flat directory of closing_*.json (the host's exports/, the laptop's
exports/host/) or a tree of dated folders <YYYY-MM-DD>/ (the mirror's host/), read through
scripts/qb_hold_receipt.read_closings over src/walters/redated.closing_rows (the one reader); latest/ is refused (by
name, resolved, or behind a dated-named link) and any other subfolder never read; not a directory is refused. The
population is every closing row of family SOCCER whose row competition is "PL" and row season is "2026/27", one row
per match: the last in-bound run's (earlier runs counted and printed as a count, never read). This receipt does NOT
inherit #688's FLOOR (2026-10-20T18:42:00Z, #615's stamping; scripts/pl_injury_classification_receipt.population):
that floor is #688's issue's, not "every PL closing row of 2026/27", so the population here is a local one with
#688's other rules (one row per match, the last run, a copy in two folders one run). Optional --from INSTANT
(inclusive) and --through INSTANT (exclusive) bound the closing run's start, each a UTC instant YYYY-MM-DDTHH:MM:SSZ
parsed by qb_hold_receipt.parse_instant; --from not before --through is refused. A PL row with no run start is
counted and never read (law 4).
From each row (the page's own keys; never the stored factor_breakdown, whose fenced arms the page strips):
injuries.{home,away}_count, injuries.{home,away}_names (the first 8 only, src/walters/export.py:598),
input_quality.injuries.<side>.{count,synced_at}, prediction.factor_breakdown.{home,away}_injuries_count and
factor_notes, match_id, utc_date, home_team, away_team, season, competition; the file's exported_at and git_sha; the
closing block's start and run_id.

THE COPY (--db COPY, required): the host's pulled .backup copy, opened only through addendum 198 item 6(ii)'s fence
exactly as #688 opens it (its check_copy, probe_copy and open_db: mlb_pitchers_gate.check_db, a -wal/-shm/-journal
sidecar refused, mlb_pitchers_gate.open_ro before any read, mlb_pitchers_gate.readonly_session with
mode=ro&immutable=1). Every refusal exits 2 with nothing read. From it: (1) PRAGMA table_info(injuries) on the copy's
own connection (never database.has_injury_player_id, which inspects the app's engine): is player_source_id present;
if present, how many injuries rows of PL 2026/27 teams carry a non-null one (counts only). (2) Through #688's read_db
(the match by id only when its teams and kickoff agree, else by both team names and the kickoff) and #688's
recoverable() test (the stored refreshed_at equals the row's synced_at and the counts match): for a recoverable side,
each paired entry's stored type, fixture_source_id and player_position. No name is printed.

THE RULE (declared here and printed on the console before any result line):
- The fold is #688's tokens() (NFKD, combining marks dropped, casefold, apostrophes dropped, dots and hyphens to
  spaces, split), imported, never re-implemented.
- Pairs are formed only between two entries of the SAME side of the SAME row.
- "accent": the raw strings differ (after strip) and the folded token tuples are equal.
- "double surname": the token tuples differ, the shorter has at least 2 tokens, both share the first token, and the
  shorter's tokens are an order-kept sub-sequence of the longer's (so "Given S1" and "Given S2" each pair with
  "Given S1 S2"; with all three on one side the long form is AMBIGUOUS).
- "initial form" (#688's _initial_form, either direction): printed APART, never in the headline (the order names only
  accents and the double surname), never subtracted from a distinct count.
- "identical": the same raw string twice (after strip); its own kind. The adapter dedupes by the exact stripped name
  (src/adapters/api_football.py:459, :477-479), so 0 is expected: measured, never assumed.
- An entry that would pair with two or more other entries (by any kind above) is AMBIGUOUS: counted, never paired, and
  its candidates are not paired with it (as #688's name_match).
- A side whose count is above 8 has its names cut (export.py:598): counted apart as "names cut, not fully pairable"
  (law 4); pairs among its 8 shown names still count, labelled.
- A side whose names list is shorter than its count for any other reason is counted with its cause.
- Distinct players by name fold, per side = entries - (accent + double surname + identical pairs); pairs are disjoint
  by construction. "at most" where the names are cut or short.
- Distinct players by the source's own player id: the page carries no id (export.py:592-600) and soccer stores none
  (api_football.py:460-475 never reads player.id; src/ingestion/service.py:1571-1581 writes player_source_id only when
  an adapter supplies one; of the three list_injuries adapters, only src/adapters/api_american_football.py:529 (its
  list_injuries at :441) does). So every pair's "two ids or one" reads UNKNOWN, printed once with these causes and the
  copy's PRAGMA result, its cause measured on the copy: "no source id stored" where the column is absent or no
  injuries row of a PL 2026/27 team carries one; "not read per entry" (with the count) where some do, since this
  receipt never reads an entry's id. Never guessed.

PRIVACY (446: "the names stay off the public record; they are on the page"): the console prints NO player name, ever:
not in pairs, not in examples, not in errors. A pair is named by its row (kickoff, match id, file), side, team name and
the two entries' 1-based places in the page's names list ("entries 3 and 6"), plus its kind.

No provider call, no network, no API key; nothing written anywhere. No verdict and no de-duplication: the architect
rules on the receipt. Last line: PL-INJURY-DUPLICATE-RECEIPT {json, counts only}. Exit 0 done; 2 refused.

Run:  python3 scripts/pl_injury_duplicate_receipt.py --exports DIR|TREE --db COPY [--from INSTANT] [--through INSTANT]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load(name: str):
    """A sibling script loaded by path (as #688 loads qb_hold_receipt); its module-level imports import no src.db."""
    spec = importlib.util.spec_from_file_location(f"{name}_for_446", Path(__file__).resolve().parent / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C = _load("pl_injury_classification_receipt")     # #688: tokens, _initial_form, the fence, read_db, recoverable
redated = C.redated

TAG = "PL-INJURY-DUPLICATE-RECEIPT"
FAMILY, COMPETITION, SEASON = "SOCCER", "PL", "2026/27"
NAMES_KEPT = C.ROW_NAMES_KEPT                     # 8: export.py:598 "[:8]  # first 8 only"
ACCENT, DOUBLE, INITIAL, IDENTICAL = "accent", "double surname", "initial form", "identical"
KINDS = (ACCENT, DOUBLE, IDENTICAL, INITIAL)
HEADLINE = (ACCENT, DOUBLE)                       # the order names only these two
FOLDED = (ACCENT, DOUBLE, IDENTICAL)              # subtracted from entries for the distinct-by-fold count
NOTE = re.compile(r"^(home|away) missing (\d+) \(-(\d+)% xG\)$")   # src/models/factors.py:133-135

RULE = [
    "THE RULE (declared before any result; addendum 446 item 1, \"Counts and the rule you used\"):",
    "  fold: #688's tokens() (NFKD, combining marks dropped, casefold, apostrophes dropped, dots and hyphens to "
    "spaces, split), imported from scripts/pl_injury_classification_receipt.py",
    "  pairs only between two entries of the SAME side of the SAME row",
    f"  kind '{ACCENT}': the raw strings differ (after strip) and the folded token tuples are equal",
    f"  kind '{DOUBLE}': the token tuples differ, the shorter has >= 2 tokens, both share the first token, and the "
    "shorter's tokens are an order-kept sub-sequence of the longer's ('Given S1' and 'Given S2' each pair with "
    "'Given S1 S2')",
    f"  kind '{INITIAL}' (#688's _initial_form, either direction): printed APART, never in the headline, never "
    "subtracted",
    f"  kind '{IDENTICAL}': the same raw string twice (the adapter dedupes by the exact stripped name, "
    "api_football.py:459,477-479; measured, never assumed)",
    "  an entry that would pair with 2+ other entries (any kind) is AMBIGUOUS: counted, never paired",
    f"  a side whose count is above {NAMES_KEPT}: names cut (export.py:598), counted apart as 'names cut, not fully "
    "pairable' (law 4); pairs among its shown names still count, labelled",
    "  a side whose names list is shorter than its count for another reason: counted with its cause",
    f"  distinct by name fold = entries - ({' + '.join(FOLDED)} pairs); 'at most' where the names are cut or short",
    "  headline: rows and sides carrying >= 1 pair of the kinds " + " / ".join(repr(k) for k in HEADLINE),
    "  privacy (446): no player name is printed; an entry is its 1-based place in the page's names list",
]
ID_CAUSES = ("the page carries no player id (src/walters/export.py:592-600); the soccer adapter never reads player.id "
             "(src/adapters/api_football.py:460-475) and keeps one entry per exact stripped name (:459,477-479); "
             "injuries.player_source_id is written only when an adapter supplies one (src/ingestion/service.py:"
             "1571-1581), and of the three list_injuries adapters only src/adapters/api_american_football.py:529 "
             "(list_injuries at :441) supplies one")


def id_cause(pr: dict) -> str:
    """The UNKNOWN's cause, measured on the copy (law 4): 'no source id stored' only where the column is absent or no
    injuries row of a PL 2026/27 team carries one; otherwise this receipt's own limit (it never reads an entry's id)."""
    if not pr["present"] or not pr["with_id"]:
        return "no source id stored"
    return (f"not read per entry by this receipt; {pr['with_id']} injuries rows of PL {SEASON} teams carry a non-null "
            "player_source_id")


class Refused(Exception):
    """A refused read: exit 2, nothing read."""


# ---- the rule -------------------------------------------------------------------------------------------------------

def _subseq(short: tuple, long: tuple) -> bool:
    it = iter(long)
    return all(t in it for t in short)


def pair_kind(a, b) -> str | None:
    """The kind two raw entries of one side pair by, else None (THE RULE)."""
    ra, rb = str(a).strip(), str(b).strip()
    ta, tb = C.tokens(ra), C.tokens(rb)
    if not ta or not tb:
        return None
    if ra == rb:
        return IDENTICAL
    if ta == tb:
        return ACCENT
    short, long = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len(short) >= 2 and len(short) < len(long) and short[0] == long[0] and _subseq(short, long):
        return DOUBLE
    if C._initial_form(ta, tb) or C._initial_form(tb, ta):
        return INITIAL
    return None


def side_pairs(names: list) -> tuple[list[tuple[int, int, str]], list[int]]:
    """([(i, j, kind)] with 1-based places, i < j), [ambiguous places]: an entry with 2+ candidates is AMBIGUOUS, and
    no pair touches an ambiguous entry, so the pairs are disjoint."""
    n = len(names)
    cand = {i: [] for i in range(n)}
    for i in range(n):
        for j in range(i + 1, n):
            k = pair_kind(names[i], names[j])
            if k:
                cand[i].append((j, k))
                cand[j].append((i, k))
    amb = {i for i, c in cand.items() if len(c) > 1}
    pairs = [(i + 1, j + 1, k) for i in range(n) for j, k in cand[i]
             if i < j and i not in amb and j not in amb]
    return pairs, sorted(i + 1 for i in amb)


# ---- the rows -------------------------------------------------------------------------------------------------------

def bounds(from_: str | None, through: str | None) -> tuple[datetime | None, datetime | None]:
    """(lo, hi), naive UTC, through qb_hold_receipt.parse_instant; no floor (critic G2: #688's is its issue's)."""
    qb = C._qb_hold()
    try:
        lo = qb.parse_instant(from_, "--from") if from_ is not None else None
        hi = qb.parse_instant(through, "--through") if through is not None else None
    except qb.Refused as e:
        raise Refused(f"REFUSED: {e}") from None
    if lo is not None and hi is not None and not lo < hi:
        raise Refused(f"REFUSED: --from {qb._z(lo)} is not before --through {qb._z(hi)}: the window holds no run "
                      "start; nothing read")
    return lo, hi


def _ours(e) -> bool:
    """A closing entry (run, family, row) of this population: family SOCCER, row competition PL, row season 2026/27."""
    return C._pl(e) and e[2].get("season") == SEASON


def file_index(exports: Path) -> dict:
    """{(match id, run start): {file, git_sha, exported_at, run_id}}: #688's file_index (the same folders, order and
    run start) widened by the file's exported_at and the closing block's run_id."""
    out = {}
    for sub, pre in C.closing_dirs(exports):
        for p in sorted(sub.glob(redated.CLOSING_GLOB)):
            try:
                doc = json.loads(p.read_text())
                block = doc.get("closing") or {}
                run = redated.as_utc(block.get("start"))
                preds = [r for r in doc.get("predictions") or [] if isinstance(r, dict)]
                meta = {"file": pre + p.name, "git_sha": doc.get("git_sha"), "exported_at": doc.get("exported_at"),
                        "run_id": block.get("run_id")}
            except (OSError, ValueError, AttributeError, TypeError):
                continue
            stamp = redated._STAMP.search(p.name)
            if run is None and stamp:
                run = datetime.strptime(stamp.group(1), "%Y-%m-%dT%H%M")
            for r in preds:
                out[(r.get("match_id"), run)] = meta
    return out


def population(exports: Path, lo: datetime | None, hi: datetime | None) -> dict:
    """The local population (no FLOOR, unlike #688's population(), critic G2): every SOCCER closing row with row
    competition PL and row season 2026/27, one per match, the last in-bound run's; earlier runs counted. The latest/
    refusals are #688's, word for word in effect."""
    if not exports.is_dir():
        raise Refused(f"REFUSED: --exports {exports}: not a directory; nothing read")
    if "latest" in (exports.name, exports.resolve().name):
        raise Refused(f"REFUSED: --exports {exports}: a latest/ folder (resolves to {exports.resolve()}); latest/ is "
                      "never read (its files are copies of a dated folder's newest); pass its parent; nothing read")
    for sub, _pre in C.closing_dirs(exports)[1:]:
        if sub.resolve().name == "latest":
            raise Refused(f"REFUSED: --exports {exports}: the dated folder {sub.name}/ resolves to {sub.resolve()}, a "
                          "latest/ folder; latest/ is never read; nothing read")
    cr = C._qb_hold().read_closings(exports, lo, hi)
    idx = file_index(exports)
    rows, no_run, earlier, other_season = [], [], 0, 0
    for mid, runs in sorted(cr["rows"].items()):
        other_season += sum(1 for x in runs if C._pl(x) and x[2].get("season") != SEASON)
        keep = [x for x in runs if _ours(x)]
        no_run += [mid for x in keep if x[0] is None]
        keep = [x for x in keep if x[0] is not None]
        if not keep:
            continue
        run, _fam, r = keep[-1]
        n_earlier = len({x[0] for x in keep} - {run})      # a file copied into two folders is one run
        earlier += n_earlier
        rows.append({"match_id": mid, "run": run, "earlier_runs": n_earlier, "row": r,
                     "meta": idx.get((mid, run), {})})
    rows.sort(key=lambda x: (x["run"], x["match_id"]))
    out_b = {k: sum(1 for v in cr[k].values() for x in v if _ours(x)) for k in ("outside", "unknown")}
    return {"rows": rows, "files": cr["files"], "unreadable": cr["unreadable"], "dated": cr["dated"],
            "repeated": cr["repeated"], "dir": exports.resolve(), "lo": lo, "hi": hi, "no_run": sorted(set(no_run)),
            "earlier": earlier, "other_season": other_season, "bound_outside": out_b["outside"],
            "bound_unknown": out_b["unknown"]}


def _int(v) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def analyse_side(r: dict, side: str) -> dict:
    """One side's entries, pairs and labels, from the page (never a name kept for printing)."""
    base = C.row_side(r, side)                     # team, count (input_quality), count_block, names, synced_at
    page = _int(base["count_block"])
    entries = page if page is not None else base["count"]
    names = base["names"]
    shown = len(names) if names is not None else 0
    pairs, amb = side_pairs(names or [])
    cut = entries is not None and entries > NAMES_KEPT
    short = None
    if entries is None:
        short = "count unknown (no injuries.<side>_count and no input_quality count on the page)"
    elif names is None and entries > 0:
        short = "no names list on the page"
    elif not cut and shown < entries:
        short = "names list shorter than the count (count <= 8; the cause is not on the page)"
    elif not cut and shown > entries:
        short = "names list longer than the count"
    by = Counter(k for _i, _j, k in pairs)
    folded = sum(by[k] for k in FOLDED)
    fb = C._d(C._d(r.get("prediction")).get("factor_breakdown"))
    fcount = _int(fb.get(f"{side}_injuries_count"))
    note = None
    for n in fb.get("factor_notes") or []:
        m = NOTE.match(str(n))
        if m and m.group(1) == side:
            note = {"count": int(m.group(2)), "pct": int(m.group(3))}
    return {"team": base["team"], "entries": entries, "page_count": page, "iq_count": base["count"],
            "shown": shown, "names": names, "pairs": pairs, "ambiguous": amb, "by": by, "cut": cut, "short": short,
            "distinct": None if entries is None else entries - folded,
            "at_most": bool(cut or (short and entries is not None and shown < entries)),
            "fcount": fcount, "note": note,
            "factor_equal": None if fcount is None or entries is None else fcount == entries}


# ---- the copy -------------------------------------------------------------------------------------------------------

def pragma(s) -> dict:
    """PRAGMA table_info on the copy's own connection (critic G3: never database.has_injury_player_id, which reads
    the app's engine): is injuries.player_source_id present, and if so the PL 2026/27 teams' rows carrying one."""
    from sqlalchemy import text
    cols = {row[1] for row in s.execute(text("PRAGMA table_info(injuries)"))}
    mcols = {row[1] for row in s.execute(text("PRAGMA table_info(matches)"))}
    if "season" not in mcols:
        raise Refused("REFUSED: columns season not in matches (law 1)")
    teams = ("SELECT m.home_team_id FROM matches m JOIN competitions c ON c.id = m.competition_id "
             "WHERE c.code = :code AND m.season = :season UNION SELECT m.away_team_id FROM matches m JOIN "
             "competitions c ON c.id = m.competition_id WHERE c.code = :code AND m.season = :season")
    args = {"code": COMPETITION, "season": SEASON}
    rows_pl = s.execute(text(f"SELECT count(*) FROM injuries WHERE team_id IN ({teams})"), args).scalar()
    if "player_source_id" not in cols:
        return {"present": False, "pl_rows": rows_pl, "with_id": None}
    with_id = s.execute(text(f"SELECT count(*) FROM injuries WHERE player_source_id IS NOT NULL AND team_id IN "
                             f"({teams})"), args).scalar()
    return {"present": True, "pl_rows": rows_pl, "with_id": with_id}


def stored_of(sd: dict, place: int) -> str:
    """The paired entry's stored type / fixture_source_id / position on a recoverable side (no name printed)."""
    name = (sd["names"] or [None] * place)[place - 1]
    hits = [e for e in sd["stored"] if e["name"] == name]
    if len(hits) != 1:
        return f"entry {place}: stored entry not found once ({len(hits)} stored rows carry its exact name)"
    e = hits[0]
    return (f"entry {place}: type {e['type']!r} · fixture_source_id {e['fixture']!r} · position "
            f"{e['position']!r}")


# ---- the console ----------------------------------------------------------------------------------------------------

def _pairs_text(sd: dict) -> str:
    parts = []
    for k in KINDS:
        ps = [f"entries {i} and {j}" for i, j, kk in sd["pairs"] if kk == k]
        if ps:
            parts.append(f"{k} {len(ps)} ({'; '.join(ps)})")
    return " · ".join(parts) or "none"


def _side_line(side: str, sd: dict) -> str:
    note = (f"note {sd['note']['count']} (-{sd['note']['pct']}% xG)" if sd["note"] else "note none")
    eq = {True: "equal", False: "NOT EQUAL", None: "not compared (missing)"}[sd["factor_equal"]]
    dist = "unknown" if sd["distinct"] is None else (("at most " if sd["at_most"] else "") + str(sd["distinct"]))
    lab = []
    if sd["cut"]:
        lab.append(f"names cut, not fully pairable ({sd['entries']} entries, {sd['shown']} shown)")
    if sd["short"]:
        lab.append(sd["short"])
    amb = f"entries {', '.join(map(str, sd['ambiguous']))}" if sd["ambiguous"] else "none"
    return (f"  {side.upper()} {sd['team']}: entries {sd['entries']} (injuries.{side}_count {sd['page_count']}, "
            f"input_quality count {sd['iq_count']}) · names shown {sd['shown']} · pairs {_pairs_text(sd)} · "
            f"AMBIGUOUS {amb} · factor_breakdown {side}_injuries_count {sd['fcount']}, {note} · factor count vs page "
            f"count: {eq} · distinct by fold {dist}" + (f" · {'; '.join(lab)}" if lab else ""))


def build(pop: dict, s) -> dict:
    rows = pop["rows"]
    for x in rows:
        x["sides"] = {side: C.row_side(x["row"], side) for side in ("home", "away")}   # read_db's input
        x["a"] = {side: analyse_side(x["row"], side) for side in ("home", "away")}
    C.read_db(s, rows)                              # #688: by id when teams + kickoff agree, else teams + kickoff
    for x in rows:
        for side in ("home", "away"):
            ok, why = C.recoverable(x["sides"][side])
            x["a"][side]["recoverable"], x["a"][side]["why"] = ok, why
            x["a"][side]["stored"] = x["sides"][side].get("stored") or []
    return {"rows": rows, "pragma": pragma(s)}


def lines(res: dict, pop: dict, label: str, exports_arg: str) -> tuple[list[str], dict]:
    qb = C._qb_hold()
    rows, pr = res["rows"], res["pragma"]
    era, run_text = qb.run_label(pop["lo"], pop["hi"])
    L = [f"PL INJURY DUPLICATE RECEIPT (ARCHITECT 2026-11-22, addendum 446 item 1; Refs #1052) · READ-ONLY · no "
         f"provider call, nothing written · database {label}",
         f"closing files {pop['dir']} (--exports {exports_arg}; closing_*.json there and in its dated folders "
         f"<YYYY-MM-DD>/ {pop['dated']}, never latest/; qb_hold_receipt.read_closings over redated.closing_rows) · "
         f"closing files read {pop['files']} · family {FAMILY}, row competition {COMPETITION}, row season {SEASON}; "
         f"no floor (#688's FLOOR is its issue's, not this population's)",
         f"BOUND: this run: {run_text} · --from {qb._z(pop['lo']) if pop['lo'] else '—'} (inclusive) · --through "
         f"{qb._z(pop['hi']) if pop['hi'] else '—'} (exclusive) · PL {SEASON} closing rows outside the bound "
         f"{pop['bound_outside']} · with no run start under the bound {pop['bound_unknown']} (not read, not counted)",
         *RULE]
    if pop["unreadable"]:
        L.append(f"unreadable closing files {len(pop['unreadable'])}: {', '.join(pop['unreadable'])}")
    if pop["repeated"]:
        L.append(f"closing-file names in more than one folder {len(pop['repeated'])} (each copy read; one run): "
                 f"{', '.join(pop['repeated'])}")
    if pop["no_run"]:
        L.append(f"PL {SEASON} rows with no run start (not read; law 4): matches {pop['no_run']}")
    idl = (f"the copy: PRAGMA table_info(injuries) has player_source_id; injuries rows of PL {SEASON} teams "
           f"{pr['pl_rows']}, carrying a non-null player_source_id {pr['with_id']}" if pr["present"] else
           f"the copy: PRAGMA table_info(injuries) has NO player_source_id column; injuries rows of PL {SEASON} teams "
           f"{pr['pl_rows']}")
    L.append(f"SOURCE IDS: every pair's 'two source ids or one' and every side's 'distinct by the source's own player "
             f"id' read UNKNOWN ({id_cause(pr)}): {ID_CAUSES}; {idl}.")
    quiet = 0
    tot = Counter()
    for x in rows:
        r, meta, a = x["row"], x["meta"], x["a"]
        loud = [sd for sd in a.values() if sd["pairs"] or sd["ambiguous"]]
        if not loud:
            quiet += 1
            continue
        sha = str(meta.get("git_sha") or "?")[:8]
        L.append(f"\n== kickoff {r.get('utc_date')} UTC · match {x['match_id']} {r.get('home_team')} v "
                 f"{r.get('away_team')} · file {meta.get('file')} (git_sha {sha}, exported_at "
                 f"{meta.get('exported_at')}, run {x['run']:%Y-%m-%dT%H:%MZ}, run_id {meta.get('run_id')}; earlier "
                 f"runs {x['earlier_runs']})")
        for side in ("home", "away"):
            sd = a[side]
            L.append(_side_line(side, sd))
            if sd["pairs"]:
                L.append(f"    recoverable? {'yes' if sd['recoverable'] else 'no'} ({sd['why']})")
                if sd["recoverable"]:
                    for i, j, k in sd["pairs"]:
                        L.append(f"    {k} pair entries {i} and {j}: {stored_of(sd, i)} | {stored_of(sd, j)}")
    sides = [sd for x in rows for sd in x["a"].values()]
    for sd in sides:
        tot.update(sd["by"])
    head_side = [sd for sd in sides if any(sd["by"][k] for k in HEADLINE)]
    head_rows = [x for x in rows if any(any(sd["by"][k] for k in HEADLINE) for sd in x["a"].values())]
    shorts = Counter(sd["short"] for sd in sides if sd["short"])
    fdiff = [x for x in rows if any(sd["factor_equal"] is False for sd in x["a"].values())]
    fmiss = sum(1 for sd in sides if sd["factor_equal"] is None)
    rec_pairs = sum(1 for sd in sides if sd["pairs"] and sd["recoverable"])
    L.append(f"\nrows with no pair and no ambiguity: {quiet} (one count line; none of their sides carries a pair of "
             "any kind or an ambiguous entry)")
    L.append("TOTALS:")
    L.append(f"  rows read (one per match) {len(rows)} · earlier runs not counted {pop['earlier']} · PL rows of "
             f"another season (not read) {pop['other_season']} · sides {len(sides)} · entries "
             f"{sum(sd['entries'] or 0 for sd in sides)} (sides with the count unknown "
             f"{sum(1 for sd in sides if sd['entries'] is None)})")
    L.append(f"  HEADLINE ({' / '.join(HEADLINE)}): rows with >= 1 pair {len(head_rows)} · sides with >= 1 pair "
             f"{len(head_side)}")
    L.append("  pairs by kind: " + " · ".join(f"{k} {tot[k]}" for k in KINDS)
             + f" ({INITIAL} apart, never in the headline)")
    L.append(f"  ambiguous entries {sum(len(sd['ambiguous']) for sd in sides)} (sides "
             f"{sum(1 for sd in sides if sd['ambiguous'])})")
    L.append(f"  sides with names cut, not fully pairable {sum(1 for sd in sides if sd['cut'])} (of them carrying a "
             f"headline pair among the shown names {sum(1 for sd in head_side if sd['cut'])})")
    L.append("  sides whose names list is short or unknown, by cause: "
             + (" · ".join(f"{k} {v}" for k, v in sorted(shorts.items())) or "none"))
    L.append(f"  source ids: UNKNOWN for every pair and every side ({id_cause(pr)}; the SOURCE IDS line above)")
    L.append(f"  rows whose factor_breakdown count differs from the page count {len(fdiff)} · sides not compared "
             f"(a count missing) {fmiss}")
    L.append(f"  sides carrying a pair that are recoverable on this copy {rec_pairs}")
    summary = {
        "rows": len(rows), "closing_files": pop["files"], "earlier_runs": pop["earlier"],
        "other_season_rows": pop["other_season"], "no_run_start": len(pop["no_run"]),
        "bound": {"era": era, "from": qb._z(pop["lo"]) if pop["lo"] else None,
                  "through": qb._z(pop["hi"]) if pop["hi"] else None, "outside": pop["bound_outside"],
                  "unknown": pop["bound_unknown"]},
        "sides": len(sides), "entries": sum(sd["entries"] or 0 for sd in sides),
        "headline_rows": len(head_rows), "headline_sides": len(head_side),
        "pairs": {k: tot[k] for k in KINDS},
        "ambiguous_entries": sum(len(sd["ambiguous"]) for sd in sides),
        "sides_names_cut": sum(1 for sd in sides if sd["cut"]), "sides_short": dict(shorts),
        "source_ids": f"unknown ({id_cause(pr)})",
        "player_source_id_column": pr["present"], "pl_injury_rows": pr["pl_rows"], "pl_rows_with_id": pr["with_id"],
        "rows_factor_differs": len(fdiff), "sides_factor_not_compared": fmiss,
        "sides_with_pair_recoverable": rec_pairs,
        "matches_with_headline_pair": [x["match_id"] for x in head_rows],
        "exports_dir": str(pop["dir"]), "dated_folders": pop["dated"]}
    L.append(TAG + " " + json.dumps(summary, sort_keys=True, default=str))
    return L, summary


def main(argv=None, echo=print) -> int:
    ap = argparse.ArgumentParser(description="addendum 446 item 1 (Refs #1052): the PL injury duplicate receipt")
    ap.add_argument("--exports", default=None,
                    help="REQUIRED: the closing files, a flat directory of closing_*.json (the host's exports/, the "
                         "laptop's exports/host/) or a tree of dated folders <YYYY-MM-DD>/ (the mirror's host/); "
                         "latest/ refused")
    ap.add_argument("--db", default=None,
                    help="REQUIRED: the host's pulled .backup copy OUTSIDE data/, opened mode=ro + immutable=1 "
                         "(addendum 198 item 6(ii)); without it, exit 2, nothing read")
    ap.add_argument("--from", dest="from_", default=None, metavar="INSTANT",
                    help="bound the closing run's start, INCLUSIVE, a UTC instant YYYY-MM-DDTHH:MM:SSZ")
    ap.add_argument("--through", default=None, metavar="INSTANT",
                    help="bound the closing run's start, EXCLUSIVE, a UTC instant YYYY-MM-DDTHH:MM:SSZ")
    a = ap.parse_args(argv)
    try:
        try:
            path = C.check_copy(a.db)                 # first: without a copy nothing is read
        except C.Refused as e:
            raise Refused(str(e)) from None
        if a.exports is None or not str(a.exports).strip():
            raise Refused("REFUSED: --exports is required (a flat directory of closing_*.json or a tree of dated "
                          "folders); nothing read")
        lo, hi = bounds(a.from_, a.through)
        try:
            C.probe_copy(path)                        # the copy opens before any read
        except C.Refused as e:
            raise Refused(str(e)) from None
        pop = population(Path(a.exports), lo, hi)
        with C.open_db(path) as (s, label):
            try:
                res = build(pop, s)
            except C.Refused as e:
                raise Refused(str(e)) from None
        out, _summary = lines(res, pop, label, a.exports)
    except Refused as e:
        echo(str(e))
        return 2
    for ln in out:
        echo(ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
