#!/usr/bin/env python3
"""THE BULLETIN RENDERER (ARCHITECT 2026-11-04 11:20 ET, addendum 250 items 1-4; step 1b of the bulletins lane, #826;
ordered by addendum 289 item 4). READ-ONLY machinery: it reads one closing file or one slate file and writes Markdown
and a PNG card per game, under exports/bulletins/ only.

    python cli.py bulletin --closing-file PATH | --slate-file PATH [--out-dir exports/bulletins] [--db PATH]
    (= python deploy/hosting/bulletin.py --closing-file PATH | --slate-file PATH [--out-dir DIR] [--db PATH])

Addendum 250 item 1, in part: "One file pair per game per stage: `<match_id>_<away-slug>_at_<home-slug>_closing.md` +
`.png` (the closing page's row) and `..._slate.md` + `.png` (the slate file's row), under
`exports/bulletins/<FAMILY>/<ET date of kickoff>/` (`closing.ny_date`, the day rule coverage already uses; slugs are the
team names lower-cased, ASCII-folded, non-alphanumerics to hyphens). The row is the export's own row [...]; the bulletin
computes nothing the row does not carry, and a field the row lacks prints "not stored" (law 4), never a default."
Sections, in the ruled order, every one present: (a) the headline, (b) the call, (c) the prediction, (d) the teams,
(e) the market, (f) the maths, (g) what changed since the slate, (h) the footer, verbatim (FOOTER).

THE CALL LINE is closing.call_text(row, desk), IMPORTED and printed verbatim; the would-be line is closing.would_be_text
on the Desk row closing.desk_rows builds (the one the summary block prints), labelled "record only, not placed"; the
quarantine, value shadow and kalshi-only hold lines are closing.summary_block's own lines for the row, verbatim.

THE CARD (item 1): "a phone-sized portrait card (1080 px wide), matplotlib's Agg backend with its bundled DejaVu Sans
(no display, no system font)". Drawn on a matplotlib Figure with the Agg canvas (never pyplot, never a display), every
text with a FontProperties naming the DejaVu Sans file inside matplotlib's own mpl-data (never a font looked up on the
system); width CARD_WIDTH_PX, the height grown to what the card holds (portrait: never under CARD_MIN_HEIGHT_PX).

THE PRIVACY RULE (item 2), IN THE WRITER: no desk.order text, no desk.exec.contracts, no fee_order_contracts, no contract
count, no dollar figure, no desk_meta.unit.fraction / half_fraction, no pool figure, no account id, no API key. By
construction: the renderer reads a fixed list of fields and none of those (an order prints as side, venue and the limit
in cents, and only an order that was written; stakes in units only). By guard: every row value is put on one line
(one_line: no value spans two lines of either file) and every "$" of the Markdown is escaped (no row text renders as
math on GitHub; the card draws every text with parse_math=False), sp_common.redact runs over every line (host.env read
first, as the units read it) and a line it redacted REFUSES the run (ARCHITECT 2026-11-08, addendum 298 B item 5: "A
secret in the source: REFUSE, do not redact"; pattern `secret`), then src/privacy_patterns.bulletin_offence (the #817 patterns, one definition, plus the
bulletin's own) runs over the WHOLE Markdown and every string the card draws, line by line as written, line by line as
rendered and the whole text as rendered (entities decoded, NFKC, line breaks one space), for every file of the run,
BEFORE anything is written. A match REFUSES THE WRITE: nothing of the
run is written, the receipt carries `bulletin_refused` with each pattern's NAME and the file's intended path, never the
line, and the command exits 2. The writer writes only .md and .png (exports_mirror.BULLETIN_SUFFIXES): a .json, or any
other suffix, is refused by the writer itself (item 4: "NO JSON is ever written under it").

THE LINKS (item 4): the console prints each written file's mirror URL,
https://github.com/<owner>/<repo>/blob/main/<role>/bulletins/<FAMILY>/<date>/<file>, the owner/repo parsed from
SP_EXPORTS_MIRROR_REMOTE (never the setting's value printed), the role SP_EXPORTS_MIRROR_ROLE; a remote that does not
parse, an unset remote or role, or an --out-dir that is not the mirror's subtree (exports/bulletins) prints why there
is no URL instead.

THE DB (item 3): only for PL's matchday, opened mode=ro (sp_common.ro_connect on the configured DB), or --db on a copy
(mlb_pitchers_gate.check_db's fence; sp_common.copy_connect: mode=ro + immutable=1, addendum 198 item 6(ii)). A DB that
cannot be read prints "not stored" with the reason; it never fails the render.

RECEIPT: kind "bulletin" (sp_common.append_receipt): source, stage, family, exit, written (paths), skipped (match id,
why; a match id that is not an integer is skipped and never a path segment), and bulletin_refused [{pattern, path}]
or bulletin_failed (the redacted error; withheld to its type and the pattern's name where the guard matches it). Exit 0 written (or nothing to
render), 2 refused (an argument, a file that is not the stage's kind, or the guard), 1 failed.

NOT HERE (addendum 289 item 4 "no timer yet"): the two closing.py hooks of item 3 (the closing run and the slate stage
calling this command before the mirror push) are not built; nothing calls this command unattended. Step 2 (the weekly
digest, item 5) is its own PR.
"""
from __future__ import annotations

import argparse
import fnmatch
import io
import json
import os
import re
import sys
import textwrap
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sp_common as c  # noqa: E402
import closing as cl  # noqa: E402
import exports_mirror as em  # noqa: E402

if str(HERE.parents[1]) not in sys.path:
    sys.path.insert(0, str(HERE.parents[1]))
from src.privacy_patterns import bulletin_offence, rendered  # noqa: E402

KIND = "bulletin"
STAGES = ("closing", "slate")
OUT_DIR = "exports/bulletins"                 # item 3's default; the mirror's kept subtree (exports_mirror.BULLETINS)
NOT_STORED = "not stored"                     # item 1: "a field the row lacks prints "not stored" (law 4)"
# Item 1 (h), verbatim.
FOOTER = ("A record of our model's view against the market at the time stamped above. Not advice. A PASS is the usual "
          "outcome; a PLAY is a Desk call under its own rules, sized in units. Generated by sports_predictor on the "
          "host; the closing page is the call.")
EMPTY_LIST_WARNING = "a list we could not read, not a team with nobody hurt"    # addendum 40 item 4, as item 1(d) quotes
NO_SLATE_ROW = "no slate row for this game (first sight at the closing)"         # item 1(g), verbatim
SLATE_CHANGE = "the closing bulletin will carry the change"                      # item 1(g), verbatim
RECORD_ONLY = "record only, not placed"                                          # item 1(b), verbatim
CLOSING_STAGE = f"closing page, T-{cl.RUN_LEAD_MIN}"                             # item 1(a): "closing page, T-35"
VENUE = "Kalshi"
SIDES = ("HOME", "DRAW", "AWAY")
PROB_KEY = {"HOME": "home_win", "DRAW": "draw", "AWAY": "away_win"}
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
CARD_WIDTH_PX = 1080                          # item 1: "a phone-sized portrait card (1080 px wide)"
CARD_MIN_HEIGHT_PX = 1350                     # portrait: never shorter than 4:5
CARD_DPI = 100
# The reference palette (dataviz skill, references/palette.md, light): surface, ink, and the categorical slots 1-3 in
# fixed order (validated: CVD and normal-vision floors pass; the aqua slot's contrast warning is relieved by a value
# label on every bar).
CARD_BG, INK, INK_2 = "#fcfcfb", "#0b0b0b", "#52514e"
SERIES = (("model", "#2a78d6"), ("books fair", "#eb6834"), ("Kalshi normalized", "#1baf7a"))


class Refused(Exception):
    """An argument or an input the command will not render (exit 2)."""


# ------------------------------------------------------------------------------------------------- values --

def v(x) -> str:
    """A value as the row gives it, else "not stored" (law 4: never a default)."""
    if x is None:
        return NOT_STORED
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, (list, tuple)):
        return ", ".join(str(i) for i in x) if x else "none listed"
    return str(x)


_BREAKS = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029]+")       # Cc, Zl and Zp: a run of them is one space


def one_line(text) -> str:
    """A text on ONE line: every control character (line feed, carriage return, tab, vertical tab, form feed, the C1
    set) and the Unicode line and paragraph separators, a run of them one space, so no row value can span two lines of the Markdown
    or of the card (the guard reads what is drawn, and what is drawn is one line per value)."""
    return _BREAKS.sub(" ", str(text))


def md_line(line) -> str:
    """One Markdown line as written: on one line, redacted (sp_common.redact), and every "$" escaped so GitHub never
    renders a row's text as math (an inline $...$ would draw something the guard never read)."""
    return c.redact(one_line(line)).replace("$", "\\$")


def pp(x) -> str:
    return NOT_STORED if x is None else f"{x:+.2f}pp"


def cents(x) -> str:
    """A price in dollars-per-contract (0.49) as cents (49c); formatting, never a re-derivation."""
    if x is None or isinstance(x, bool):
        return NOT_STORED
    try:
        return f"{round(float(x) * 100, 2):g}c"
    except (TypeError, ValueError):
        return NOT_STORED


def pct(x) -> str:
    if x is None or isinstance(x, bool):
        return "n/s"
    return f"{float(x) * 100:.1f}%"


def get(d, *path):
    """A nested read: d[path[0]][path[1]]..., None where any step is missing or not a dict."""
    for k in path:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def slug(name) -> str:
    """Item 1: "the team names lower-cased, ASCII-folded, non-alphanumerics to hyphens" (a run of them one hyphen,
    none at either end); an empty result is "team"."""
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "team"


def kickoff(row) -> datetime | None:
    try:
        return cl.parse_utc(row["utc_date"]) if row.get("utc_date") else None
    except (TypeError, ValueError):
        return None


def file_stem(row, stage: str) -> str:
    return f"{row.get('match_id')}_{slug(row.get('away_team'))}_at_{slug(row.get('home_team'))}_{stage}"


def side_name(row, side) -> str:
    return {"HOME": row.get("home_team"), "AWAY": row.get("away_team"), "DRAW": "Draw"}.get(side) or str(side)


def sides_of(row, fam: str) -> tuple:
    """The row's selections: HOME/DRAW/AWAY where it carries a draw (the soccer 1X2), else HOME/AWAY."""
    probs = get(row, "prediction", "probabilities") or {}
    three = fam == "SOCCER" or probs.get("draw") is not None or "DRAW" in ((get(row, "market", "selections") or {}))
    return SIDES if three else ("HOME", "AWAY")


def model_p(row, side):
    """The model's probability of a selection as the row carries it: prediction.probabilities (soccer, MLB) or
    prediction.home_win_prob / away_win_prob (NFL)."""
    pr = row.get("prediction") or {}
    probs = pr.get("probabilities")
    if isinstance(probs, dict):
        return probs.get(PROB_KEY[side])
    return pr.get({"HOME": "home_win_prob", "AWAY": "away_win_prob"}.get(side, "-"))


def books_fair(row, side):
    m = row.get("market") or {}
    sel = get(m, "selections", side)
    if isinstance(sel, dict):
        return sel.get("fair_prob")
    return get(m, "fair_prob", side)


def kalshi_norm(row, side):
    """market.kalshi.prob (the sum-normalized legs) where the row carries it; NFL's kalshi_prob is the HOME side only."""
    k = get(row, "market", "kalshi")
    if isinstance(k, dict) and isinstance(k.get("prob"), dict):
        return k["prob"].get(side)
    return row.get("kalshi_prob") if side == "HOME" else None


def kalshi_mid(row, side):
    """The Kalshi mid of a leg as the row stores it (market.kalshi.raw_yes_prob: the bid/ask midpoint)."""
    return get(row, "market", "kalshi", "raw_yes_prob", side)


# ------------------------------------------------------------------------------------------------- inputs --

def _family_of_slate(name: str) -> str | None:
    hits = [f for f, spec in cl.FAMILIES.items() if fnmatch.fnmatch(name, spec["export_glob"])]
    return hits[0] if len(hits) == 1 else None


def load(path: Path, stage: str) -> tuple[dict, str]:
    """(doc, family) of a closing file (closing.closing_doc's shape: a `closing` block naming the family, else the
    name's closing_<FAMILY>_ segment) or a slate file (the family whose export_glob the name matches; a file with a
    closing block is never read as a slate file, addendum 40 item 2). Refused otherwise."""
    if not path.is_file():
        raise Refused(f"no file at {path}")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Refused(f"{path.name} cannot be parsed: {type(e).__name__}")
    if not isinstance(doc, dict) or not isinstance(doc.get("predictions"), list):
        raise Refused(f"{path.name} holds no predictions list: not an export")
    if stage == "closing":
        block = doc.get("closing")
        if not isinstance(block, dict):
            raise Refused(f"{path.name} has no closing block: not a closing file (closing.closing_doc)")
        fam = block.get("family")
        if not fam:
            m = re.match(r"closing_([A-Z]+)_", path.name)
            fam = m.group(1) if m else None
    else:
        if "closing" in doc:
            raise Refused(f"{path.name} is a closing file: a closing file is never read as a slate file")
        fam = _family_of_slate(path.name)
    if fam not in cl.FAMILIES:
        raise Refused(f"{path.name}: no closing family named (the families: {', '.join(cl.FAMILIES)})")
    return doc, fam


def desk_row(doc: dict, row: dict, fam: str) -> dict | None:
    """The Desk row closing.desk_rows builds for this row (the one the summary block prints), never re-derived here."""
    rows = cl.desk_rows({"predictions": [row]}, {row.get("match_id")}, EPOCH, fam=fam)
    return rows[0] if rows else None


def _entry_certification(eid: str) -> str | None:
    """The registry entry's own `certification` text (docs/registry/experiments.json), read-only; None unread."""
    try:
        from src.walters import registry
        e = next((x for x in registry.load(registry.LEDGER) if isinstance(x, dict) and x.get("id") == eid), None)
    except Exception:                                   # noqa: BLE001  (a line, never the render's failure)
        return None
    return str(e["certification"]) if isinstance(e, dict) and e.get("certification") else None


def certification_line(fam: str, row: dict) -> str:
    """Item 1(a): the family's certification as the code reads it now, never a hand-written state. NFL:
    closing.nfl_certification() on nfl_predict.MODEL_VERSION. SOCCER and MLB: registry.certification_of on the row's
    own prediction.model_version. An uncertified model prints the withholding entry's own certification text verbatim
    and its id; the would-be clause only for a family closing writes a would-be line for (closing.WOULD_BE_FAMILIES).
    A model the registry holds no entry for is "certification not read" with certification_of's reason (law 4: "a
    missing entry is not a certification", registry.certification_of), never an inferred "live"."""
    mv = get(row, "prediction", "model_version")
    if fam == "NFL":
        try:
            from src.walters.nfl_predict import MODEL_VERSION
            mv = MODEL_VERSION
        except Exception:                               # noqa: BLE001  (a line, never the render's failure)
            pass
        state, why = cl.nfl_certification()
    elif mv:
        try:
            from src.walters import registry
            state, why = registry.certification_of(mv)
        except Exception as e:                          # noqa: BLE001
            state, why = "unread", type(e).__name__
    else:
        return f"model version {NOT_STORED}: certification not read"
    if state == "uncertified":
        text = _entry_certification(why) or "UNCERTIFIED"
        tail = (": market-only, the would-be call below is a record, not a pick"
                if fam in cl.WOULD_BE_FAMILIES else "")
        return f"{mv} — {text} (registry {why}){tail}"
    if state == "certified":
        return f"{mv} — certified (registry {why})"
    return f"{mv} — certification not read ({why})"


def matchday(fam: str, row: dict, db: Path | None, cache: dict) -> str:
    """Item 1(a): NFL the row's `week`; PL the DB's matches.matchday (mode=ro; --db a copy, immutable); else not
    stored."""
    if fam == "NFL":
        return v(row.get("week"))
    if fam != "SOCCER":
        return NOT_STORED
    if "con" not in cache:
        try:
            cache["con"] = c.copy_connect(db) if db is not None else c.ro_connect(c.db_path())
            cache["why"] = None
        except Exception as e:                          # noqa: BLE001  (law 4: unread, labelled, never fatal)
            cache["con"], cache["why"] = None, f"the DB cannot be read: {type(e).__name__}"
    if cache["con"] is None:
        return f"{NOT_STORED} ({cache['why']})"
    try:
        got = cache["con"].execute("SELECT matchday FROM matches WHERE id = ?", (row.get("match_id"),)).fetchone()
    except Exception as e:                              # noqa: BLE001
        return f"{NOT_STORED} (the DB cannot be read: {type(e).__name__})"
    return NOT_STORED if not got or got[0] is None else str(got[0])


def slate_row(exports: Path, fam: str, row: dict) -> tuple[dict | None, str | None]:
    """Item 1(g): "the same game's row in the day's slate file (the file coverage's SLATE line selects: the family's
    export_glob, exported on the ET day, holding the row, the newest)": the ET day of the kickoff, the row holding a
    desk block; (row, file name) or (None, None)."""
    ko = kickoff(row)
    if ko is None or not exports.is_dir():
        return None, None
    day = cl.ny_date(ko)
    best = None
    for p in sorted(exports.glob(cl.FAMILIES[fam]["export_glob"])):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            at = cl.parse_utc(doc["exported_at"])
            hit = next((r for r in doc.get("predictions") or []
                        if isinstance(r, dict) and r.get("match_id") == row.get("match_id") and r.get("desk")), None)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
        if hit is None or "closing" in doc or cl.ny_date(at) != day:
            continue
        if best is None or (at, p.name) > best[0]:
            best = ((at, p.name), hit, p.name)
    return (best[1], best[2]) if best else (None, None)


# ----------------------------------------------------------------------------------------------- markdown --

def _order_line(d: dict) -> str:
    """Item 2: "orders print as side, venue and the limit in cents, never a count", and only an order that was WRITTEN
    (desk_policy.order_line sets side and limit before it finds the size under one contract and writes no text: that
    order does not exist, and closing.order_text says "no order"). The order's why is printed only
    where it is the unit-unread text (addendum 179 item 4); any other why names the unit's basis, so it stays on the
    closing page."""
    o = d.get("order") or {}
    if o.get("text") and o.get("side") and o.get("limit") is not None:     # written (never the text itself)
        return f"order: {o['side']} on {VENUE}, limit {cents(o['limit'])}"
    if o.get("why") == cl.UNIT_UNREAD_TEXT:
        return f"order: {cl.UNIT_UNREAD_TEXT}"
    return "order: none written (the reason is on the closing page)"


def section_call(row: dict, d: dict, x: dict | None, fam: str) -> list[str]:
    call = cl.call_text(row, d)
    out = ["## THE CALL", "", f"# {call}", ""]
    reasons = [str(r) for r in d.get("reasons") or []]
    if d.get("call") not in cl.STAKED_CALLS:
        why = d.get("reason") or d.get("pass_kind") or NOT_STORED
        out += [f"**WHY THERE IS NO BET:** {why}", ""]
    out.append(f"- reason: {v(d.get('reason'))}")
    for r in reasons:
        out.append(f"  - {r}")
    out += [f"- pass_kind: {v(d.get('pass_kind'))}", f"- tier: {v(d.get('tier'))}",
            f"- tags: {v(d.get('tags'))}"]
    if fam == "NFL":
        out.append(f"- QB: {cl.qb_class(d)}")
    hold = cl.hold_for(d, fam)
    if hold:
        out.append(f"- HOLD: {hold}")
    if d.get("call") in cl.STAKED_CALLS:
        out.append(f"- {_order_line(d)}")
    if x and x.get("would_be"):
        out.append("- " + " · ".join(cl.would_be_text(x["would_be"])))
    if x:
        for line in cl.summary_block(x).split("\n"):
            s = line.strip()
            if s.startswith(("value shadow", "quarantine shadow", "kalshi-only hold")):
                out.append(f"- {s}")
    return out + [""]


def section_prediction(row: dict, fam: str) -> list[str]:
    pr = row.get("prediction") or {}
    out = ["## THE PREDICTION", "", f"- model_version: {v(pr.get('model_version'))}",
           f"- computed_at: {v(pr.get('computed_at'))}"]
    for s in sides_of(row, fam):
        out.append(f"- {side_name(row, s)} ({s.lower()}): {v(model_p(row, s))}")
    out += [f"- top pick: {v(pr.get('top_pick'))} at {v(pr.get('top_pick_prob'))}", f"- tier: {v(pr.get('tier'))}"]
    if fam == "SOCCER":
        out += [f"- expected goals: {row.get('home_team')} {v(pr.get('expected_home'))} · "
                f"{row.get('away_team')} {v(pr.get('expected_away'))}",
                f"- most likely score: {v(get(pr, 'factor_breakdown', 'most_likely_score'))}"]
    elif fam == "NFL":
        out.append(f"- margin line (consensus home spread): {v(get(row, 'market', 'consensus_home_spread'))} · "
                   f"total line: {NOT_STORED}")
    else:
        out.append(f"- expected runs: {row.get('home_team')} {v(pr.get('expected_home'))} · "
                   f"{row.get('away_team')} {v(pr.get('expected_away'))}")
    return out + [""]


def section_teams(row: dict, d: dict, fam: str) -> list[str]:
    iq = row.get("input_quality") or {}
    fb = get(row, "prediction", "factor_breakdown") or {}
    out = ["## THE TEAMS", ""]
    for side in ("home", "away"):
        team = row.get(f"{side}_team")
        out.append(f"### {team} ({side})")
        if fam == "NFL":
            out.append(f"- Elo: {v(row.get('elo_' + side))} (source {NOT_STORED})")
        else:
            out.append(f"- Elo: {v(fb.get(side + '_elo'))} (source {v(get(iq, 'rating_source', side))})")
        if fam == "SOCCER":
            out.append(f"- attack {v(fb.get(side + '_attack'))} · defence {v(fb.get(side + '_defense'))} "
                       f"(source {v(get(iq, 'strengths_source', side))})")
        f = row.get(f"{side}_form")
        if isinstance(f, dict):
            out.append(f"- form (last 5): {v(f.get('last_5'))} · W-D-L {v(f.get('wins'))}-{v(f.get('draws'))}-"
                       f"{v(f.get('losses'))} · goals for {v(f.get('goals_scored'))}, against "
                       f"{v(f.get('goals_conceded'))}")
        else:
            out.append(f"- form (last 5): {NOT_STORED}")
        if fam == "NFL":
            inj = get(iq, "injuries", side)
            if isinstance(inj, dict):
                out += [f"- injuries: {v(inj.get('count'))} listed (synced {v(inj.get('synced_at'))})",
                        f"- QB listed: {v(inj.get('qb_listed'))}",
                        f"- positions_unresolved: {v(inj.get('positions_unresolved'))}",
                        f"- injured by name: {v(inj.get('names'))}"]
            else:
                out.append(f"- injuries: {NOT_STORED}")
        elif fam == "MLB":
            p = get(row, "pitchers", side)
            out.append(f"- starter: {v(p.get('name'))} ({v(p.get('kind'))}, ERA {v(p.get('era'))})"
                       if isinstance(p, dict) else f"- starter: {NOT_STORED}")
            inj = row.get("injuries")
            out.append(f"- injuries: {v(inj.get(side + '_count'))} · {v(inj.get(side + '_names'))}"
                       if isinstance(inj, dict) else f"- injuries: {NOT_STORED}")
        else:
            inj = row.get("injuries")
            if isinstance(inj, dict):
                out.append(f"- injuries: {v(inj.get(side + '_count'))} · {v(inj.get(side + '_names'))}")
            else:
                out.append(f"- injuries: {NOT_STORED}")
            out.append(f"- injury list synced: {v(get(iq, 'injuries', side, 'synced_at'))}")
        out.append("")
    if fam == "SOCCER":
        out += [f"- strengths backfilled: {v(iq.get('strengths_backfilled'))} · current-season matches: "
                f"{v(iq.get('current_season_matches'))}",
                f"- factor notes: {v(fb.get('factor_notes'))}",
                f"- injuries_synced_at: {v(iq.get('injuries_synced_at'))}"]
    if fam == "NFL":
        out += [f"- QB class: {cl.qb_class(d)}", f"- positions_unresolved (both sides): "
                f"{v(cl.unresolved_injuries(row))}",
                f"- Elo gap: {v(row.get('elo_gap'))} · home advantage applied: {v(row.get('home_adv_applied'))}"]
    for team in cl.injuries_empty(row):
        out.append(f"- WARNING {team}: an empty injury list, {EMPTY_LIST_WARNING}")
    return out + [""]


def section_market(row: dict, fam: str, books: dict | None) -> list[str]:
    m = row.get("market") or {}
    ko = kickoff(row)
    out = ["## THE MARKET", "", "### The books"]
    sels = m.get("selections")
    for s in sides_of(row, fam):
        sel = (sels or {}).get(s) if isinstance(sels, dict) else None
        if isinstance(sel, dict):
            out.append(f"- {side_name(row, s)}: best {v(sel.get('best_price'))} ({v(sel.get('best_bookmaker'))}) · "
                       f"fair {v(sel.get('fair_prob'))} · model edge {pp(sel.get('edge_pp'))}")
        else:
            out.append(f"- {side_name(row, s)}: fair {v(get(m, 'fair_prob', s))} (best price {NOT_STORED})")
    out += [f"- bookmaker_count: {v(m.get('bookmaker_count'))} (quoted {v(m.get('bookmaker_count_quoted'))}) · "
            f"overround: {v(m.get('overround_pct'))}%" if m.get("overround_pct") is not None else
            f"- bookmaker_count: {v(m.get('bookmaker_count'))} (quoted {v(m.get('bookmaker_count_quoted'))}) · "
            f"overround: {NOT_STORED}"]
    if fam == "NFL":
        out.append(f"- fair source: {v(m.get('fair_source'))}")
    if books is not None:
        out.append(f"- books: {books['why']}" if books.get("why") else f"- books: {v(books.get('n'))} priced")
    out += ["", "### Kalshi"]
    k = m.get("kalshi") if isinstance(m.get("kalshi"), dict) else {}
    legs = row.get("kalshi_legs") or {}
    for s in sides_of(row, fam):
        leg = legs.get(s) if isinstance(legs, dict) else None
        if not isinstance(leg, dict):
            out.append(f"- {side_name(row, s)}: leg {NOT_STORED}")
            continue
        out.append(f"- {side_name(row, s)}: {v(leg.get('ticker'))} · bid {cents(leg.get('bid'))} / ask "
                   f"{cents(leg.get('ask'))} · raw {v(get(k, 'raw_yes_prob', s))} · normalized "
                   f"{v(kalshi_norm(row, s))} · vs book {pp(get(k, 'vs_book_pp', s))}")
    cap = k.get("captured_at") or row.get("kalshi_captured_at")
    age = NOT_STORED
    try:
        if cap and ko:
            age = f"{(ko - cl.parse_utc(cap)).total_seconds() / 60:.0f} min before kickoff"
    except (TypeError, ValueError):
        pass
    out.append(f"- captured_at: {v(cap)} ({age}) · normalized set: {v(k.get('normalized'))}")
    if fam == "NFL":
        out.append(f"- venue gap: {pp(row.get('venue_gap_pp'))} · venue flag: {v(row.get('venue_flag'))}")
    out += ["", "### Line move"]
    lm = row.get("line_move")
    if not isinstance(lm, dict):
        out.append(f"- line_move: {NOT_STORED} (null on the row)")
    else:
        out.append(f"- flag: {v(lm.get('flag'))} · window {v(lm.get('window_h'))}h · threshold "
                   f"{v(lm.get('threshold_pp'))}pp")
        for venue, mv in (lm.get("venues") or {}).items():
            if isinstance(mv, dict):
                out.append(f"- {venue}: {v(mv.get('from'))} at {v(mv.get('from_at'))} → {v(mv.get('to'))} at "
                           f"{v(mv.get('to_at'))} · move {v(mv.get('move_pp'))}pp · alarm {v(mv.get('alarm'))}")
    return out + [""]


META_RULES = ("exec_addendum", "started_rule", "venue_quote_age_rule", "mlb_quarantine_above_pp",
              "mlb_kalshi_only_suspended", "default_rating_rule", "injuries_one_sided_rule",
              "nfl_injury_list_empty_rule", "kickoff_clock_rule", "kickoff_clock_hold_h", "host_fence_rule",
              "nfl_market_only_rule", "kalshi_leg_guard")


def section_maths(row: dict, d: dict, meta: dict) -> list[str]:
    ex = d.get("exec") if isinstance(d.get("exec"), dict) else {}
    out = ["## THE MATHS", "",
           f"- edge_pp = model_p − market_ref = {v(d.get('model_p'))} − {v(d.get('market_ref'))} → "
           f"{pp(d.get('edge_pp'))} (reference: {v(d.get('reference'))})",
           f"- exec edge = model_p − cost = {v(d.get('model_p'))} − {v(ex.get('cost'))} → {pp(ex.get('edge_pp'))} "
           f"(basis {v(ex.get('basis'))})",
           f"- cost: the taker ask plus the fee at the series' fee multiplier (series {v(row.get('fee_series'))}, "
           f"taker M {v(row.get('fee_m_taker'))}) · taker cost {v(ex.get('taker_cost'))} · maker cost "
           f"{v(ex.get('maker_cost'))} · join price {v(ex.get('join_price'))}",
           f"- fee_clears: {v(ex.get('fee_clears'))} · doctrine: {v(ex.get('doctrine'))}"
           + (f" ({ex['join_note']})" if ex.get("join_note") else ""),
           f"- class: {v(d.get('cls'))} · tier: {v(d.get('tier'))} · pass_kind: {v(d.get('pass_kind'))}"]
    kc = d.get("kickoff_clock")
    if isinstance(kc, dict):
        out.append(f"- kickoff clock: stored {v(kc.get('stored_kickoff'))} vs Kalshi {v(kc.get('kalshi_clock'))} · "
                   f"drift {v(kc.get('drift_h'))}h (max {v(kc.get('max_drift_h'))}h)")
    out.append(f"- policy {v(meta.get('policy_version'))} as of {v(meta.get('as_of'))}; the rules in force:")
    for k in META_RULES:
        out.append(f"  - {k}: {v(meta.get(k))}")
    return out + [""]


def _then_now(label: str, then, now) -> str:
    return f"- {label}: {v(then)} → {v(now)}"


def section_change(row: dict, d: dict, stage: str, exports: Path, fam: str) -> list[str]:
    out = ["## WHAT CHANGED SINCE THE SLATE", ""]
    if stage == "slate":
        return out + [f"- {SLATE_CHANGE}", ""]
    old, name = slate_row(exports, fam, row)
    if old is None:
        return out + [f"- {NO_SLATE_ROW}", ""]
    od = old.get("desk") or {}
    pick = d.get("pick") or od.get("pick")
    out.append(f"- the slate row: exports/{name}")
    out.append(_then_now("call", cl.call_text(old, od), cl.call_text(row, d)))
    for s in sides_of(row, fam):
        out.append(_then_now(f"model {side_name(row, s)}", model_p(old, s), model_p(row, s)))
    out += [_then_now(f"books fair on the pick ({v(pick)})", books_fair(old, pick), books_fair(row, pick)),
            _then_now(f"Kalshi mid on the pick ({v(pick)})", kalshi_mid(old, pick), kalshi_mid(row, pick)),
            _then_now("edge", pp(od.get("edge_pp")), pp(d.get("edge_pp"))),
            _then_now("exec edge", pp(get(od, "exec", "edge_pp")), pp(get(d, "exec", "edge_pp")))]
    for side in ("home", "away"):
        a, b = get(old, "injuries", side + "_names"), get(row, "injuries", side + "_names")
        if not isinstance(a, list) or not isinstance(b, list):
            out.append(f"- injuries {row.get(side + '_team')}: added/removed {NOT_STORED}")
            continue
        add, rem = [n for n in b if n not in a], [n for n in a if n not in b]
        out.append(f"- injuries {row.get(side + '_team')}: added {v(add)} · removed {v(rem)}")
    return out + [""]


def stage_text(stage: str, doc: dict) -> str:
    """Item 1(a)'s stage: "closing page, T-35" or "slate, <exported_at> ET" (not stored where the file has none)."""
    if stage == "closing":
        return CLOSING_STAGE
    return f"slate, {cl.et(cl.parse_utc(doc['exported_at']))}" if doc.get("exported_at") else f"slate, {NOT_STORED}"


def markdown(row: dict, d: dict, x: dict | None, *, fam: str, stage: str, stage_s: str, doc: dict, run_id, week: str,
             cert: str, exports: Path, books: dict | None) -> str:
    ko = kickoff(row)
    lines = [f"# {row.get('away_team')} at {row.get('home_team')}", "",
             f"- competition: {v(row.get('competition'))} (family {fam})",
             f"- matchweek: {week}",
             f"- kickoff: {cl.et(ko)} ({cl.iso_z(ko)})",
             f"- stage: {stage_s}",
             f"- run id: {v(run_id)}",
             f"- certification: {cert}", ""]
    lines += section_call(row, d, x, fam)
    lines += section_prediction(row, fam)
    lines += section_teams(row, d, fam)
    lines += section_market(row, fam, books)
    lines += section_maths(row, d, doc.get("desk_meta") or {})
    lines += section_change(row, d, stage, exports, fam)
    lines += ["---", "", FOOTER, ""]
    return "\n".join(md_line(line) for line in lines)


# --------------------------------------------------------------------------------------------------- card --

def card_spec(row: dict, d: dict, *, fam: str, stage_s: str, week: str, cert: str, run_id) -> dict:
    """What the card draws (item 1): the headline, the call line and reason, the probabilities beside the books' fair
    and Kalshi's normalized as grouped bars, the edge and exec edge, the injury counts, the certification line and the
    footer. Every string it draws is in `texts` (the guard reads them all)."""
    ko = kickoff(row)
    sides = sides_of(row, fam)
    if fam == "NFL":
        inj = [get(row, "input_quality", "injuries", s, "count") for s in ("home", "away")]
    else:
        inj = [get(row, "injuries", s + "_count") for s in ("home", "away")]
    head = [f"{row.get('away_team')} at {row.get('home_team')}",
            f"{v(row.get('competition'))} · matchweek {week} · {stage_s}",
            f"kickoff {cl.et(ko)} ({cl.iso_z(ko)}) · run {v(run_id)}"]
    bars = [[(model_p(row, s), books_fair(row, s), kalshi_norm(row, s))[i] for s in sides] for i in range(3)]
    groups = [side_name(row, s)[:18] for s in sides]
    values = [pct(x) for series in bars for x in series]
    info = [f"edge {pp(d.get('edge_pp'))} · exec edge {pp(get(d, 'exec', 'edge_pp'))}",
            f"injuries listed: {row.get('home_team')} {v(inj[0])} · {row.get('away_team')} {v(inj[1])}",
            cert]
    def t(x):                                    # on one line and redacted, as every Markdown line is
        return c.redact(one_line(x))
    spec = {"head": [t(x) for x in head], "call": t(cl.call_text(row, d)),
            "reason": t(d.get("reason") or d.get("pass_kind") or NOT_STORED),
            "bars": bars, "groups": [t(g) for g in groups], "values": values,
            "legend": [n for n, _ in SERIES], "info": [t(x) for x in info], "footer": FOOTER}
    spec["texts"] = (spec["head"] + [spec["call"], spec["reason"]] + spec["groups"] + values + spec["legend"]
                     + spec["info"] + [FOOTER])
    return spec


def _fonts():
    """matplotlib's own bundled DejaVu Sans (mpl-data/fonts/ttf), by file: never a font looked up on the system."""
    import matplotlib
    from matplotlib.font_manager import FontProperties
    ttf = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    reg, bold = ttf / "DejaVuSans.ttf", ttf / "DejaVuSans-Bold.ttf"
    if not reg.is_file():
        raise RuntimeError("matplotlib's bundled DejaVu Sans is missing from its mpl-data")

    def font(size, heavy=False):
        return FontProperties(fname=str(bold if heavy and bold.is_file() else reg), size=size)
    return font


def render_card(spec: dict) -> bytes:
    """The PNG card (Agg, no display): CARD_WIDTH_PX wide, portrait. Drawn under matplotlib's own defaults (an rc
    context reset to rcdefaults, restored after): no matplotlibrc, MPLCONFIGDIR or style on the host can change the
    width (savefig.bbox), turn text into TeX (text.usetex) or anything else the card draws."""
    import matplotlib
    with matplotlib.rc_context():
        matplotlib.rcdefaults()
        return _render_card(spec)


def _render_card(spec: dict) -> bytes:
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.patches import Patch
    font = _fonts()
    pad, w = 54, CARD_WIDTH_PX
    blocks = []                               # (text, size, heavy, color, gap after) in px
    for i, t in enumerate(spec["head"]):
        blocks += [(ln, 34 if i == 0 else 22, i == 0, INK if i == 0 else INK_2, 6)
                   for ln in textwrap.wrap(t, 44 if i == 0 else 78)]
    blocks.append(("", 10, False, INK, 10))
    blocks += [(ln, 60, True, INK, 4) for ln in textwrap.wrap(spec["call"], 26)]
    blocks += [(ln, 22, False, INK, 4) for ln in textwrap.wrap(spec["reason"], 76)]
    top = [(t, s, h, col, g) for t, s, h, col, g in blocks]
    info = []
    for t in spec["info"]:
        info += [(ln, 22, False, INK, 4) for ln in textwrap.wrap(t, 76)]
    foot = [(ln, 17, False, INK_2, 3) for ln in textwrap.wrap(spec["footer"], 100)]

    def height(bs):
        return sum(int(s * 1.35) + g for _, s, _, _, g in bs)
    chart_h = 560
    h = max(CARD_MIN_HEIGHT_PX, pad + height(top) + 30 + chart_h + 30 + height(info) + 30 + height(foot) + pad)
    fig = Figure(figsize=(w / CARD_DPI, h / CARD_DPI), dpi=CARD_DPI, facecolor=CARD_BG)
    canvas = FigureCanvasAgg(fig)
    y = pad

    def draw(bs, y):
        for t, s, heavy, col, g in bs:
            if t:
                fig.text(pad / w, 1 - y / h, t, fontproperties=font(s * 0.72, heavy), color=col, va="top",
                         ha="left", parse_math=False)
            y += int(s * 1.35) + g
        return y
    y = draw(top, y) + 30
    ax = fig.add_axes([pad / w, 1 - (y + chart_h - 70) / h, 1 - 2 * pad / w, (chart_h - 110) / h])
    ax.set_facecolor(CARD_BG)
    n, k = len(spec["groups"]), len(SERIES)
    width = 0.8 / k
    for i, (name, col) in enumerate(SERIES):
        for j, val in enumerate(spec["bars"][i]):
            xpos = j + (i - (k - 1) / 2) * width
            if val is None:
                ax.text(xpos, 0.01, "n/s", ha="center", va="bottom", color=INK_2, fontproperties=font(11),
                        parse_math=False)
                continue
            ax.bar(xpos, float(val), width * 0.92, color=col, label=name if j == 0 else None)
            ax.text(xpos, float(val) + 0.01, spec["values"][i * n + j], ha="center", va="bottom", color=INK,
                    fontproperties=font(11), parse_math=False)
    tops = [float(x) for series in spec["bars"] for x in series if x is not None]
    ax.set_ylim(0, min(1.05, max(tops + [0.5]) + 0.15))
    ax.set_xlim(-0.5, n - 0.5)
    ax.set_yticks([])
    ax.set_xticks(range(n))
    ax.set_xticklabels(spec["groups"], fontproperties=font(14), parse_math=False)    # a team's $...$ is text
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(INK_2)
    ax.tick_params(axis="x", colors=INK, length=0)
    handles = [Patch(color=col, label=name) for name, col in SERIES]
    ax.legend(handles=handles, prop=font(12), frameon=False, loc="upper center", ncol=k,
              bbox_to_anchor=(0.5, 1.12))
    y += chart_h + 30
    y = draw(info, y) + 30
    draw(foot, y)
    buf = io.BytesIO()
    canvas.print_png(buf)                    # the canvas itself: no savefig.bbox crop, the figure's own dpi
    return buf.getvalue()


# ------------------------------------------------------------------------------------------------- writer --

def write_file(path: Path, data: bytes) -> None:
    """The ONE writer (item 4: "NO JSON is ever written under it"): .md and .png only (exports_mirror
    .BULLETIN_SUFFIXES), atomically (a temporary name beside it, then the rename), never under data/ (law 5)."""
    if path.suffix not in em.BULLETIN_SUFFIXES:
        what = path.suffix or "a file with no suffix"
        raise Refused(f"the bulletin writer writes {' and '.join(em.BULLETIN_SUFFIXES)} only, never {what}")
    c.refuse_under_data(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def mirror_url(rel: str, out_dir: Path) -> str:
    """Item 4's link for one written file, or why there is none. The owner/repo is parsed from
    SP_EXPORTS_MIRROR_REMOTE; the setting's value is never printed."""
    if out_dir.resolve() != (c.REPO / OUT_DIR).resolve():
        return "no mirror URL: --out-dir is not the mirror's subtree (exports/bulletins)"
    remote = c.setting(cl.MIRROR_SETTING)
    role = (c.setting(cl.ROLE_SETTING) or "").strip()          # as closing.push_mirror strips it
    if not remote:
        return f"no mirror URL: {cl.MIRROR_SETTING} unset"
    if role not in cl.ROLES:
        return f"no mirror URL: {cl.ROLE_SETTING} unset or neither host nor laptop"
    m = re.fullmatch(r"(?:git@github\.com:|ssh://git@github\.com/|https://github\.com/)([A-Za-z0-9_.-]+)/"
                     r"([A-Za-z0-9_.-]+?)(?:\.git)?/?", remote.strip())
    if not m:
        return f"no mirror URL: {cl.MIRROR_SETTING} does not name a github.com owner/repo"
    return f"https://github.com/{m.group(1)}/{m.group(2)}/blob/{em.BRANCH}/{role}/{em.BULLETINS}/{rel}"


# -------------------------------------------------------------------------------------------------- run --

def plan(doc: dict, fam: str, stage: str, source: Path, out_dir: Path, db: Path | None) -> tuple[list, list]:
    """([(rel path, bytes-or-spec, text the guard reads)], skipped) for every row the Desk saw."""
    files, skipped, cache = [], [], {}
    run_id = (doc.get("closing") or {}).get("run_id") if stage == "closing" else None
    books = {b.get("match_id"): b for b in get(doc, "closing", "books") or [] if isinstance(b, dict)}
    stage_s = stage_text(stage, doc)
    try:
        for row in doc.get("predictions") or []:
            mid = row.get("match_id") if isinstance(row, dict) else None
            if not isinstance(mid, int) or isinstance(mid, bool):     # the file name's first segment: never a path
                skipped.append((None, "match_id not an integer"))
                continue
            if not isinstance(row.get("desk"), dict):
                skipped.append((mid, "no desk block"))
                continue
            ko = kickoff(row)
            if ko is None:
                skipped.append((mid, "no utc_date: no ET date folder"))
                continue
            d = row["desk"]
            x = desk_row(doc, row, fam)
            week = matchday(fam, row, db, cache)
            cert = certification_line(fam, row)
            md = markdown(row, d, x, fam=fam, stage=stage, stage_s=stage_s, doc=doc, run_id=run_id, week=week,
                          cert=cert, exports=source.parent, books=books.get(mid) if fam == "MLB" else None)
            spec = card_spec(row, d, fam=fam, stage_s=stage_s, week=week, cert=cert, run_id=run_id)
            base = f"{fam}/{cl.ny_date(ko).isoformat()}/{file_stem(row, stage)}"
            files.append((base + ".md", md.encode("utf-8"), md))
            files.append((base + ".png", spec, "\n".join(spec["texts"])))
    finally:
        if cache.get("con") is not None:
            cache["con"].close()
    return files, skipped


def shown(out: Path, rel: str) -> str:
    """A file's path as the receipt and the console name it: exports/bulletins/<rel> under the mirror's subtree,
    else the path under --out-dir (item 2: "the file's intended path")."""
    return f"{OUT_DIR}/{rel}" if out.resolve() == (c.REPO / OUT_DIR).resolve() else str(out / rel)


SECRET_PATTERN = "secret"
REDACTED_MARK = "[REDACTED]"                       # what sp_common.redact writes in place of a key


def secret_offence(text: str) -> str | None:
    """ARCHITECT 2026-11-08 15:20 ET, addendum 298 B item 5, verbatim: "A secret in the source: REFUSE, do not redact —
    a key in a Desk output is an upstream bug and a written file hides it." Every Markdown line and every card string
    passes sp_common.redact before the guard reads it, so a key in the source reads as the redaction mark here: the
    run is refused under `secret`, and the key itself is never in the receipt or on the console.
    Addendum 299 item 1: the key rule also reads the guard's NORMALIZED text (privacy_patterns.rendered: entities
    decoded, NFKC, format characters dropped), so a credential written with a zero-width or a fullwidth character
    ("api\u200b_key=...", "api_key\uff1d...") is refused too: either reading matching refuses."""
    if REDACTED_MARK in text:
        return SECRET_PATTERN
    norm = rendered(text)
    return SECRET_PATTERN if c.redact(norm) != norm else None


def refused_path(out: Path, rel: str, pattern: str | None = None) -> str:
    """A refused file's path for the receipt and the console: the folder (family and ET date), the match id and the
    suffix, the FILE NAME WITHHELD with the refusing pattern's name. ARCHITECT 2026-11-08 16:25 ET, addendum 299 item 1:
    "withhold the file name on EVERY refusal — the receipt names the pattern and the game id only". The file name
    carries the team names through slug(), which destroys the marker of a refused value in them (api_key= becomes
    api-key-, $25 becomes 25), so no reading of the path can be trusted to find it (Codex #894 rounds 3 and 4)."""
    hit = pattern or "the guard"
    folder, _, name = rel.rpartition("/")
    return (f"{c.redact(shown(out, folder))}/{name.split('_', 1)[0]}_…{Path(name).suffix} "
            f"(file name withheld: matched {hit})")


def error_text(e: BaseException, typed: bool = True) -> str:
    """A refusal's or a failure's text for the receipt and the console: redacted, on one line, and WITHHELD where the
    privacy guard matches it (an exception's message can quote a row's value: then the type and the pattern's name
    only). `typed` False: a Refused's own message, without the type in front."""
    msg = c.redact(one_line(f"{type(e).__name__}: {e}" if typed else str(e)))
    # addendum 301 item 1: every failure message passes the SAME guard as a rendered file, the secret reading too (a
    # render that throws on a secret-bearing value carries it in the exception text), before it is receipted or printed
    hit = bulletin_offence(msg) or secret_offence(msg)
    return f"{type(e).__name__} (message withheld: matched {hit})" if hit else msg[:300]


def run(closing_file: str | None = None, slate_file: str | None = None, out_dir: str | None = None,
        db: str | None = None, echo=print) -> int:
    c.load_host_env()                         # a by-hand run redacts host.env's keys as the units do (EnvironmentFile)
    stage = "closing" if closing_file else "slate"
    source = Path(closing_file or slate_file or "")
    rec = {"kind": KIND, "stage": stage, "source": str(source), "family": None, "written": [], "skipped": []}
    try:
        if bool(closing_file) == bool(slate_file):
            raise Refused("give exactly one of --closing-file PATH and --slate-file PATH")
        out = Path(out_dir) if out_dir else c.REPO / OUT_DIR
        out = out if out.is_absolute() else (Path.cwd() / out)
        try:
            c.refuse_under_data(out)
        except SystemExit as e:
            raise Refused(str(e))
        dbp = None
        if db is not None:
            from src.walters import mlb_pitchers_gate as mp
            try:
                dbp = mp.check_db(db)
            except mp.GateRefused as e:
                raise Refused(str(e))
        doc, fam = load(source, stage)
        rec["family"] = fam
        files, skipped = plan(doc, fam, stage, source, out, dbp)
        rec["skipped"] = [{"match_id": m, "why": w} for m, w in skipped]
        refused = [{"pattern": name, "path": refused_path(out, rel, name)} for rel, _, text in files
                   for name in [bulletin_offence(text) or secret_offence(text)] if name]
        if refused:                           # item 2: nothing written, the pattern's NAME and the path, never the line
            rec.update(exit=2, bulletin_refused=refused)
            c.append_receipt(rec)
            echo(f"BULLETIN REFUSED {fam} {stage}: {len(refused)} file(s) matched the privacy guard; nothing written")
            for r in refused:
                echo(f"  {r['pattern']}: {r['path']}")
            return 2
        root = out.resolve()
        for rel, _, _ in files:                       # every path inside --out-dir, checked before any write
            if not (out / rel).resolve().is_relative_to(root):
                raise Refused(f"a bulletin path leaves {shown(out, '')}: nothing written")
        blobs = [(rel, data if isinstance(data, bytes) else render_card(data)) for rel, data, _ in files]
        for rel, data in blobs:
            write_file(out / rel, data)
            rec["written"].append(shown(out, rel))
    except Refused as e:
        rec.update(exit=2, error=error_text(e, typed=False))
        c.append_receipt(rec)
        echo(f"BULLETIN REFUSED: {rec['error']}")
        return 2
    except Exception as e:                    # noqa: BLE001  (receipted, never a traceback without a record)
        rec.update(exit=1, bulletin_failed=error_text(e))
        c.append_receipt(rec)
        echo(f"BULLETIN FAILED: {rec['bulletin_failed']}")
        return 1
    rec["exit"] = 0
    c.append_receipt(rec)
    echo(f"BULLETIN {fam} {stage}: {len(rec['written'])} file(s) written from {source.name}"
         + (f" · {len(skipped)} row(s) skipped" if skipped else ""))
    for (rel, _), path in zip(blobs, rec["written"]):
        echo(f"  {path}")
        echo(f"    {mirror_url(rel, out)}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--closing-file", default=None)
    g.add_argument("--slate-file", default=None)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--db", default=None)
    a = ap.parse_args(argv)
    return run(a.closing_file, a.slate_file, a.out_dir, a.db)


if __name__ == "__main__":
    sys.exit(main())
