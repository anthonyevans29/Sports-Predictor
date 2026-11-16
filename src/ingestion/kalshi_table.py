"""
THE MATCHER'S NAME TABLES (ARCHITECT 2026-11-15 09:01 ET, addendum 387 item 3: "THE MATCHER: RULED, (B), THE REVIEWED
NAME TABLE"; lane #955). PR one: the machinery and no data.

Addendum 387 item 3, the rules of (B), verbatim:
"(a) a series DECLARES a table by having one; a declared series' name that is not in its table REFUSES its event under
a new counted reason that names the name; a series with no table is matched as today, to the last character.
(b) A line maps one Kalshi name to one team by the provider's key and id through Team.external_ids, so the laptop and
the host read one table; a line whose id is not among the stored teams of the series' competition refuses, and says
so. (c) A tabled name fits exactly one team; no line can loosen a fit, and the existing pins stand as they are."
(d)-(f) are the proposer's and the replay's (kalshi_table_propose.py; kalshi-replay).

How it is built here:
- A series declares a table by a file `<SERIES>.json` in TABLE_DIR (src/ingestion/kalshi_tables/). Nothing else
  declares one: there is no list in code and no competition branch. A file that cannot be read as a table does not
  undeclare its series: every event of that series is refused under TABLE_UNREADABLE (kalshi_match), never matched by
  the scorer (law 4).
- The file: {"series": "<SERIES>", "ruled": "<the ruling that made it data>", "lines": [{"name": <the Kalshi name, as
  the matcher takes it: the market's yes_sub_title, stripped>, "key": <the provider's key in Team.external_ids>,
  "id": <the provider's id, a string>}, ...]}. No other field, at either level. A name appears once; two names that
  differ only by letter case are refused as one table (the matcher's out-of-step read keys names by lower()).
- resolve(): each line's (key, id) against the stored teams of the series' competition, by
  team_merge.source_ids (a row answers to its own id and to every id a merge recorded on it). Exactly one team: the
  line's team. None, or two or more: the line is unresolved, and an event naming it is refused, saying which and why.
- tables_for(): what each caller of kalshi_match.place passes as `tables`: {series: Resolved or TableError} for every
  declared series among the markets. No declared series among them: {} and no read of the database.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

TABLE_DIR = Path(__file__).resolve().parent / "kalshi_tables"
_TOP = frozenset({"series", "ruled", "lines"})
_LINE = frozenset({"name", "key", "id"})


class TableError(ValueError):
    """A declared series' file that is not a table (law 4: its events are refused, never matched by the scorer)."""


@dataclass(frozen=True)
class Line:
    name: str
    key: str
    id: str


@dataclass(frozen=True)
class Table:
    series: str
    ruled: str
    lines: dict            # name -> Line
    path: str
    sha256: str


@dataclass
class Resolved:
    """A table read against the stored teams of its series' competition."""
    table: Table
    team_of: dict = field(default_factory=dict)     # name -> our team id (exactly one stored team answers to the line)
    unresolved: dict = field(default_factory=dict)  # name -> why (no stored team, or two or more, answer to the line)

    @property
    def series(self) -> str:
        return self.table.series


def series_of(event_ticker: str) -> str:
    """The series of an event ticker: its text before the first '-' (KXNCAAMBGAME-26NOV15ALSTSJSU -> KXNCAAMBGAME)."""
    return (event_ticker or "").split("-", 1)[0]


def declared(table_dir: Path | None = None) -> dict:
    """{series: path} of every table file. A series declares a table by having one (387 item 3(a))."""
    d = Path(table_dir) if table_dir is not None else TABLE_DIR
    if not d.is_dir():
        return {}
    return {p.stem: p for p in sorted(d.glob("*.json")) if p.is_file()}


def _no_dupes(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise TableError(f"the field {k!r} appears twice")
        out[k] = v
    return out


def load(path) -> Table:
    """The table in `path`, or TableError naming what is wrong. Strict: every rule of the module docstring."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise TableError(f"{path.name} cannot be read ({e.strerror or e})") from None
    try:
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_dupes)
    except TableError as e:
        raise TableError(f"{path.name}: {e}") from None
    except (UnicodeDecodeError, ValueError) as e:
        raise TableError(f"{path.name} is not JSON ({e})") from None
    if not isinstance(doc, dict) or set(doc) != _TOP:
        raise TableError(f"{path.name}: the top level must hold exactly {sorted(_TOP)}")
    series, ruled, lines = doc["series"], doc["ruled"], doc["lines"]
    if series != path.stem:
        raise TableError(f"{path.name}: its series {series!r} is not its file's name {path.stem!r}")
    if not isinstance(ruled, str) or not ruled.strip():
        raise TableError(f"{path.name}: 'ruled' must name the ruling that made it data")
    if not isinstance(lines, list):
        raise TableError(f"{path.name}: 'lines' must be a list")
    out, folded = {}, {}
    for i, ln in enumerate(lines, 1):
        if not isinstance(ln, dict) or set(ln) != _LINE:
            raise TableError(f"{path.name}: line {i} must hold exactly {sorted(_LINE)}")
        name, key, pid = ln["name"], ln["key"], ln["id"]
        for what, v in (("name", name), ("key", key), ("id", pid)):
            if not isinstance(v, str) or not v or v != v.strip():
                raise TableError(f"{path.name}: line {i}'s {what} must be a non-empty string with no outer space")
        if name in out:
            raise TableError(f"{path.name}: the name {name!r} has two lines")
        if name.casefold() in folded:
            raise TableError(f"{path.name}: the names {folded[name.casefold()]!r} and {name!r} differ only by case")
        out[name] = Line(name, key, pid)
        folded[name.casefold()] = name
    return Table(series=series, ruled=ruled, lines=out, path=str(path), sha256=hashlib.sha256(raw).hexdigest())


def resolve(table: Table, teams) -> Resolved:
    """Each line against `teams` (the stored teams of the series' competition: objects with id and external_ids)."""
    from src.ingestion.team_merge import source_ids

    teams = list(teams)
    res = Resolved(table)
    for name, ln in table.lines.items():
        hits = sorted(t.id for t in teams if ln.id in source_ids(t.external_ids, ln.key))
        if len(hits) == 1:
            res.team_of[name] = hits[0]
        elif not hits:
            res.unresolved[name] = (f"{ln.key} {ln.id} is not among the stored teams of the series' competition")
        else:
            res.unresolved[name] = (f"{ln.key} {ln.id} is held by {len(hits)} stored teams of the series' competition "
                                    f"(ids {', '.join(str(h) for h in hits)})")
    return res


def competition_teams(sess, comp_ids) -> list:
    """The stored teams of the competition(s): every team of a stored game of it, and every team listed in it."""
    from sqlalchemy import or_, select

    from src.db.schema import CompetitionTeam, Match, Team

    comp_ids = list(comp_ids)
    if not comp_ids:
        return []
    in_games = select(Match.home_team_id).where(Match.competition_id.in_(comp_ids)).union(
        select(Match.away_team_id).where(Match.competition_id.in_(comp_ids)))
    listed = select(CompetitionTeam.team_id).where(CompetitionTeam.competition_id.in_(comp_ids))
    return list(sess.execute(select(Team).where(or_(Team.id.in_(in_games), Team.id.in_(listed)))
                             .order_by(Team.id)).scalars())


def series_comp_ids(sess, series: str, comp_ids) -> list:
    """The run's competition ids that are THE SERIES' OWN (387 item 3(b): "the stored teams of the series'
    competition"): the one the shared map names (kalshi_sync.series_competition), where it is among the run's; a
    series the map does not name (a soccer series resolved by the adapter) on a run of one competition: that one;
    else none, so every line of it is unresolved, never read against another competition's teams."""
    from sqlalchemy import select

    from src.db.schema import Competition
    from src.ingestion.kalshi_sync import series_competition

    comp_ids = list(comp_ids)
    code = series_competition(series)
    if code is None:
        return comp_ids if len(comp_ids) == 1 else []
    own = sess.execute(select(Competition.id).where(Competition.code == code)).scalar_one_or_none()
    return [own] if own is not None and own in comp_ids else []


def tables_for(sess, markets, comp_ids, table_dir: Path | None = None) -> dict:
    """{series: Resolved or TableError} for every declared series among `markets` (kalshi_match.place's `tables`), each
    read against the stored teams of its own competition (series_comp_ids). No declared series among them: {} with
    no read of the database."""
    from src.ingestion.kalshi_match import event_of

    decl = declared(table_dir)
    present = sorted({series_of(event_of(mk)) for mk in markets} & set(decl))
    if not present:
        return {}
    out = {}
    for s in present:
        try:
            table = load(decl[s])
        except TableError as e:
            out[s] = e
            continue
        out[s] = resolve(table, competition_teams(sess, series_comp_ids(sess, s, comp_ids)))
    return out


# --------------------------------------------------------------------------------------------- the proposer ------
# ADDENDUM 387 item 3(d)-(e), verbatim: "(d) YOUR CORRECTION IS THE IMPORTANT PART AND IS ADOPTED WHOLE: a whole read is
# not proof of the right team ("Alabama A&M" reading whole on "Alabama"); the proposer MARKS for hand reading, and
# never proposes, a name or a stored name carrying a mark the tokens drop (an ampersand, a lone letter, parentheses, a
# dot other than State's), a name opening with Saint, St. or Mount, a whole read on two or more teams, and a name with
# no whole read. (e) EVERY LINE IS READ BY ME BEFORE IT IS DATA, the machine-proposed ones too; the marking orders my
# reading." And: "the read-only proposer that prints, from a kept markets file, each name with its proposed team, the
# provider's key and id, and its mark".
# A WHOLE READ: a stored team whose name has the same words as the Kalshi name under the matcher's own norm_tokens
# (kalshi_match.norm_tokens: the shared alias tokens, "St." read as State), no more and no fewer; the reading of the
# pins (addendum 59 item 2) and of the 2026-11-13 names file.
# Three marks beyond (d)'s, each only adding a name to the hand reading, never proposing one: a name the matcher pins
# (kalshi_match.PINS: its table line is a ruling as the pin was); a whole-read team with no id, or an id two stored
# teams answer to, under the key asked for (no line could be written for it); and a name another name of the series
# matches but for letter case (the loader refuses a table holding both).

MARK_DROPPED = "a mark the tokens drop"          # &, a lone letter, ( ), a dot other than State's
MARK_SAINT = "opens with Saint, St. or Mount"
MARK_MANY = "a whole read on two or more teams"
MARK_NONE = "no whole read"
MARK_PIN = "pinned in the matcher (kalshi_match.PINS)"
MARK_NO_ID = "the whole-read team has no one id under the key"
MARK_CASE = "another name of the series differs from it only by case (the loader refuses a table holding both)"

# 387 item 3(d): "a name opening with Saint, St. or Mount", however the opening is written: followed by a space, a hyphen
# or nothing ("Saint-Joseph's"), its dot followed by anything ("St.Bonaventure"), the dotless St ("St John's", which the
# tokens read as State exactly as they read "St.") and Mt.; never a word that only starts with those letters ("Stony
# Brook", "Montana") (review of PR one, P2)
_SAINT = re.compile(r"^(?:(?:Saint|Mount|St|Mt)(?![A-Za-z])|(?:St|Mt)\.)")
_STATE_DOT = re.compile(r"\bSt\.")


def dropped_marks(name: str) -> list[str]:
    """The marks in `name` that the alias tokens drop: an ampersand, a lone letter, a parenthesis, a dot other than
    the "St." of State. [] when none."""
    from src.ingestion.team_aliases import TOKEN_SYNONYMS, _PUNCT
    out = []
    if "&" in name:
        out.append("&")
    words = [TOKEN_SYNONYMS.get(w, w) for w in _PUNCT.sub(" ", (name or "").lower()).split()]
    if any(len(w) == 1 and w.isalpha() for w in words):
        out.append("a lone letter")
    if re.search(r"[()]", name or ""):
        out.append("( )")
    if "." in _STATE_DOT.sub("", name or ""):
        out.append("a dot")
    return out


@dataclass
class Proposal:
    name: str
    events: int
    whole: list            # [(team id, team name, provider id or None, why-no-id or None)]
    top: float
    top_teams: list        # [team name] scoring the top side_score
    marks: list            # [mark text]
    # 392 item 5 (ruled 408 item 5(a)): the marked section's reading aids, printed beside a hand line
    seen: list = field(default_factory=list)       # [(event ticker, the event's other name)], the markets' order
    top_ids: list = field(default_factory=list)    # [(team id, team name, provider id under --key or None)]

    @property
    def proposed(self) -> bool:
        return not self.marks


def names_of(markets: list, is_tie=None) -> dict:
    """{name: [(event ticker, the event's other name), ...]} of every name the matcher would look up: each event's
    two names, where its pair forms (kalshi_match._pair, as place() reads it), in the markets' order. The count of a
    name's events is the length of its list (addendum 392 item 5, ruled 408 item 5(a): "per name each event's ticker
    with the other name")."""
    from src.ingestion import kalshi_match as km
    is_tie = is_tie or (lambda m: False)
    by_event: dict = {}
    for mk in markets:
        by_event.setdefault(km.event_of(mk), []).append(mk)
    out: dict = {}
    for ev, mks in by_event.items():
        names, unformed = km._pair(mks, mks[0], is_tie)
        if unformed or len(names) != 2:
            continue
        for n, other in ((names[0], names[1]), (names[1], names[0])):
            out.setdefault(n, []).append((ev, other))
    return out


def _provider_id(t, key: str, teams) -> str | None:
    """The team's one provider id under `key` (its own, else the one id a merge recorded), or None where it has
    none, more than one, or one that another stored team also answers to."""
    from src.ingestion.team_merge import source_ids
    ids = source_ids(t.external_ids, key)
    own = (t.external_ids or {}).get(key)
    pid = str(own) if own is not None else (next(iter(ids)) if len(ids) == 1 else None)
    if pid is None or sum(1 for u in teams if pid in source_ids(u.external_ids, key)) != 1:
        return None
    return pid


def propose(names: dict, teams, key: str) -> list:
    """One Proposal per name (sorted by name). Pure: `teams` are objects with id, name and external_ids. `names`:
    names_of's {name: [(event ticker, other name)]}, or {name: count} where no event is at hand."""
    from src.ingestion import kalshi_match as km
    from src.ingestion.team_merge import source_ids

    teams = list(teams)
    tok = {t.id: km.norm_tokens(t.name or "") for t in teams}
    by_fold: dict = {}
    for name in names:
        by_fold.setdefault(name.casefold(), []).append(name)
    out = []
    for name in sorted(names):
        want = km.norm_tokens(name)
        whole = []
        for t in teams:
            if want and tok[t.id] == want:
                ids = source_ids(t.external_ids, key)
                own = (t.external_ids or {}).get(key)
                pid = str(own) if own is not None else (next(iter(ids)) if len(ids) == 1 else None)
                why = None
                if pid is None:
                    why = f"no {key} id" if not ids else f"{len(ids)} {key} ids"
                elif sum(1 for u in teams if pid in source_ids(u.external_ids, key)) != 1:
                    why = f"{key} {pid} answers to two or more stored teams"
                whole.append((t.id, t.name, pid, why))
        scores = [(km.side_score(name, t.name or ""), t) for t in teams]
        top = max((s for s, _ in scores), default=0.0)
        top_rows = sorted((t for s, t in scores if s == top and top > 0), key=lambda t: (t.name or "", t.id))
        top_teams = [t.name for t in top_rows]
        top_ids = [(t.id, t.name, _provider_id(t, key, teams)) for t in top_rows]
        marks = []
        dropped = sorted(set(dropped_marks(name)) | {m for _, tn, _, _ in whole for m in dropped_marks(tn or "")})
        if dropped:
            marks.append(f"{MARK_DROPPED} ({', '.join(dropped)})")
        if _SAINT.match(name):
            marks.append(MARK_SAINT)
        if len(whole) >= 2:
            marks.append(MARK_MANY)
        if not whole:
            marks.append(MARK_NONE)
        if name in km.PINS:
            marks.append(f"{MARK_PIN}: {km.PINS[name]}")
        if len(whole) == 1 and whole[0][3]:
            marks.append(f"{MARK_NO_ID}: {whole[0][3]}")
        twins = sorted(n for n in by_fold[name.casefold()] if n != name)
        if twins:
            marks.append(f"{MARK_CASE}: {', '.join(twins)}")
        v = names[name]
        seen = list(v) if isinstance(v, (list, tuple)) else []
        out.append(Proposal(name, len(seen) if seen else int(v), whole, top, top_teams, marks, seen, top_ids))
    return out
