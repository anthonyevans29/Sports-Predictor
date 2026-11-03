"""
THE QB HOLD, MEASURED (#446; ARCHITECT 2026-10-12 08:41 ET, addendum 44 item 9), READ-ONLY.

The ruling, verbatim (addendum 44 item 9): "Every NFL row the Desk calls PLAY with a QB flag or an unread list is kept
with what the page said, the price it named, the close, the result, and what was done about it. I read the receipt at
thirty such rows or at the season's end, whichever comes first. Nothing in the rule or the hold moves before that."

The build, verbatim (ARCHITECT 2026-11-02 08:30 ET, addendum 209 item 3): "the read-only receipt script of #446 is still
unbuilt and is the next ops item after today's PRs (Code: one PR, read-only, the rows from the closing and results
files, "what was done" from the ledger where a position exists, blank where none; no figure of the unit, no fill size
in the Issue)."

The would-be rows, verbatim (ARCHITECT 2026-11-02 11:20 ET, addendum 217 item 4): "#446's measurement keeps accruing on
paper — exec_cohorts and the closing page's hold check gain one cohort line for NFL while uncertified, "would-be PLAY
(uncertified, unstaked)", reading the record-only would-be call with the same QB-flag / unread-list classification,
never pooled with PLAY, never a position. #446's read at thirty rows counts those rows too, labelled."

The receipt's two questions, ruled, verbatim (ARCHITECT 2026-11-02 18:05 ET, addendum 223 item 5): "THE RECEIPT SCRIPT
PR (#446, 209 item 3) — its two questions, ruled: (a) "what was done" prints what the LEDGER holds, under the ledger's
own label for it (an operator fill prints as the ledger labels it; a would-be row with no ledger position stays blank);
the script reports and never relabels. It prints NO quantity, price, fee or P&L for any row, so a pasted console cannot
carry a fill size or let a reader infer the unit (209 item 3). (b) Results from the DB copy, as results-tally reads
them, STAYS — opened mode=ro + immutable=1 (198 item 6(ii)), the header naming the copy and the closing-file directory
as the two sources, a row whose game the copy lacks labelled "no result in this copy", never scored. It takes the slot
#800 freed."

Its three questions, ruled, verbatim (ARCHITECT 2026-11-03 07:55 ET, addendum 225 item 3): "#804 (the QB-hold receipt)
— its three questions: Q1 RULED by 2(a) above: a row the copy lacks ("no result in this copy"), a teams-differ row and a
void row each COUNT toward thirty as labelled, unscored rows, kept outside the W-L-P with their label (the change local
to collect(), as offered). Q2 CONFIRMED: "what was done" is the ledger's fills, never the Cockpit's claims (a claim is
what the page said). Q3 CONFIRMED as built: a would-be row's price line reads "none (PASS on the page)"; its exec edge
stays on the row. One push for Q1; CI green then my block. The count the script prints is the count; my "about fifteen"
was a read of the pages, not a rule."

WHAT IT READS (each reading the conservative one, law 4; the keys are printed with the output):
- THE ROWS: the NFL closing files on this machine's disk (redated.closing_rows: <exports>/closing_*.json, every file,
  never host/), the closing family NFL. One row per game, exec_cohorts' rule (the void rule's selection): the newest
  run's row whose recorded start is within the Desk's clock drift (desk_policy.DESK_CLOCK_DRIFT) of the match's
  current start; with none within it, the newest run's row, void when redated.void_label says so.
- A PLAY ROW: desk.engine model_edge, desk.call PLAY, and one of the Desk's two QB tags on desk.tags
  (exec_cohorts.QB_TAGS: "QB-flagged half units", v1.1's QB rule; "QB unread half units", the empty-list rule of
  addendum 40 item 4).
- A WOULD-BE ROW (217 item 4): desk.call PASS with pass_kind market_only (addendum 214's NFL market-only rule), its
  record-only held call desk.market_only_hold.would_call PLAY, and one of the same two QB tags on desk.tags (the
  chain's tags ride the PASS row unchanged, desk_policy.nfl_market_only). Labelled "would-be PLAY (uncertified,
  unstaked)", on its own lines, never pooled with PLAY (every count and every JSON figure is per kind; only the count
  toward thirty adds the two, labelled), never a position of the Desk's.
- WHAT THE PAGE SAID: the call and the side (desk.pick, the team named), the QB tags as the Desk wrote them, and the
  Desk's own QB reasons (desk.reasons, or market_only_hold.would_reasons on a would-be row: the lines that begin
  "QB-flagged (" or "injury list empty ("), the exec edge (desk.exec.edge_pp) and the market reference
  (desk.market_ref). No unit figure is printed (209 item 3): the size is the tag's own words ("half units").
- THE PRICE IT NAMED: a PLAY's order limit (desk.order.limit, with its limit_basis). A would-be row's page named no
  price (it was PASS): the line says so and prints no other price (223 item 5: no price or fee for any row beyond the
  page's named price and the close; the record's exec cost, the ask plus the taker fee, is not printed). Never the
  order's contracts, its unit label or its text.
- THE CLOSE: the grading close, the results' own (close.grading_close_block on the match: the book close, the Kalshi
  mid where the rulings take one; its reference printed): the close's fair probability of the page's side. Unpriced is
  printed as such, never inferred.
- THE RESULT: from the database copy, as results-tally reads them (exec_cohorts.result_of: FINISHED with both scores
  decides; a level score is a push; CANCELLED / POSTPONED / STALE_ORPHAN void; anything else open), with the final
  score away-home (223 item 5(b): the results from the DB copy STAY). The header names the two sources: the copy
  (--db) and the closing-file directory (--exports). No <sport>_results_<date>.json is opened.
- UNSCORED, COUNTED, LABELLED (225 item 3, by 225 item 2(a)): a row the hold touched counts toward thirty BEFORE the
  copy's checks; a row they leave out is kept outside the W-L-P, named beside the count by its cause, never scored
  (tallied per kind): a row whose game the copy lacks (its match id is not in the copy), labelled "no result in this
  copy" (223 item 5(b)); a row whose teams are not the copy's match (match ids are machine-local), "teams differ"; a
  void row, "re-dated void" (225 item 2(a)'s cause text), each with redated's own label (re-dated, or the placeholder
  kickoff: one void state, two labels, addendum 109 item 2 Q2; the UNSCORED line prints the head's split beside it,
  redated.void_counts: "re-dated N · placeholder kickoff M"). 225 item 2(a)'s fourth cause, non-taker basis, leaves no row out here: the receipt
  reads no cohort eligibility (no exec basis check), so a row of any basis is a scored row.
- WHAT WAS DONE (--ledger, the Cockpit's "Export ledger (JSON)" file, bd_ledger_v1_<date>.json): what the ledger holds
  on the row's game, under the ledger's own label for it (223 item 5(a)): the export's "fills" array, each entry
  printed under that key with its own field names (ticker, side, title, opened, closed) and its values as held,
  never relabelled (no "position", no side resolved to the page's). The same rule for a PLAY row and a would-be row.
  An entry is the row's game when its event ticker (the ticker less its last "-" part) is the event of the row's own
  order ticker or Kalshi legs; else when the Cockpit's game matcher fits it (src/walters/ledger_fills.py parse_ticker
  / side_fields, then game_fits on the row's teams, within a day of the ticker's date, the nearest start:
  ledger_fills._start_nearest); an entry that fits more than one row is ambiguous, counted, given to none (refusals
  stay refusals). Each entry prints on its own (a split or partial fill is its own entry); only the same entry, the
  same non-empty string id, is read once. NOTHING ELSE of an entry is printed: no quantity, price, fee, stake or P&L
  (qty, entry, exit, staked, fees, open_fee, close_fee, pnl_pre, pnl_net are never printed), and never its id (the
  CSV row it was imported from). A row with no entry is blank: "not established" (addendum 44 item 9 as addendum 46
  item 4 amended it, #446's first row: "What was done: blank, not established"). Without --ledger every row reads
  "not read (no --ledger)", never "not established". What was done is matched to the scored rows only: the LEDGER
  line's "of N" and the JSON's what_was_done are scored rows, and an unscored row is not matched to fills (said on the
  LEDGER line; 225 item 3 rules the label, not what was done for an unscored row).
- THE COUNT toward thirty: every row the hold touched, PLAY rows + would-be rows (217 item 4: counted too, labelled),
  each kind's count its scored rows + its unscored rows (225 item 3: "a row the copy lacks ("no result in this copy"),
  a teams-differ row and a void row each COUNT toward thirty as labelled, unscored rows, kept outside the W-L-P with
  their label"), beside it each kind's W-L-P / void / open (the scored rows only) and its unscored rows by cause. The
  printed count is the count (225 item 3: "The count the script prints is the count"). The one figure that adds the
  two kinds; every other count (rows with fills, not established, unscored) is printed and keyed per kind. A running
  count, never a verdict: the read is the architect's, at thirty rows or the season's end.

Refusals (exit 2, nothing read, nothing written): --db missing, empty, under the repo's data/ (the checkout's, and the
main checkout's from a worktree; by path or identity: mlb_pitchers_gate.check_db; a data/ elsewhere is not refused),
the app's configured database, no file there (never created), a -wal / -shm / -journal file beside it (immutable=1
would ignore it: nfl_v2_gate.check_db's rule), or a copy that cannot be read as the schema the read needs; --exports
not a directory, or a directory named host in any case (by its own name or through a symlink: host/ is never read,
its files carry the host's match ids); --ledger unreadable, or not a bd_ledger_v1 export (no calls array; a call or a
fill that is not an object; fills not an array; a fill whose ticker, side, title, opened or closed is present and not
a string: the Cockpit's export writes each as the CSV's string or null, and the field is named, its value never
echoed). --db opens mode=ro&immutable=1 (mlb_pitchers_gate.readonly_session; addendum 198 item 6(ii)).
Writes nothing: no database row, no ledger, no file.

Last line: QB-HOLD-RECEIPT {json} (counts only; no unit, size or dollar figure).

    python3 scripts/qb_hold_receipt.py --db COPY --exports DIR [--ledger bd_ledger_v1_<date>.json]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REFUSED = 2
FAMILY = "NFL"
READ_AT = 30
SIDECARS = ("-wal", "-shm", "-journal")      # nfl_v2_gate.check_db's rule: immutable=1 would ignore each of them
PLAY_LABEL = "PLAY (the Desk's call), QB-flagged or unread"
WOULD_LABEL = "would-be PLAY (uncertified, unstaked)"           # addendum 217 item 4, the label verbatim
NOT_ESTABLISHED = "not established"                            # addendum 46 item 4: blank where no position
NOT_READ = "not read (no --ledger)"
LEDGER_LABEL = "fills"                       # the bd_ledger_v1 export's own key for what it holds (223 item 5(a))
LEDGER_FIELDS = ("ticker", "side", "title", "opened", "closed")  # an entry's own field names; never a figure, never id
NO_RESULT = "no result in this copy"                           # addendum 223 item 5(b), the label verbatim
# the unscored rows' causes (225 item 3, by 225 item 2(a)): each counted toward thirty, labelled, never scored
UNSCORED_HEADS = (("no_result", NO_RESULT), ("teams", "teams differ"), ("void", "re-dated void"))
QB_REASON_HEADS = ("QB-flagged (", "injury list empty (")       # desk_policy's two QB reasons, as it writes them
ET = ZoneInfo("America/New_York")

RULING_44_9 = ("Every NFL row the Desk calls PLAY with a QB flag or an unread list is kept with what the page said, the "
               "price it named, the close, the result, and what was done about it. I read the receipt at thirty such "
               "rows or at the season's end, whichever comes first. Nothing in the rule or the hold moves before that.")
RULING_209_3 = ("the read-only receipt script of #446 is still unbuilt and is the next ops item after today's PRs (Code: "
                "one PR, read-only, the rows from the closing and results files, \"what was done\" from the ledger "
                "where a position exists, blank where none; no figure of the unit, no fill size in the Issue).")
RULING_217_4 = ("#446's measurement keeps accruing on paper — exec_cohorts and the closing page's hold check gain one "
                "cohort line for NFL while uncertified, \"would-be PLAY (uncertified, unstaked)\", reading the "
                "record-only would-be call with the same QB-flag / unread-list classification, never pooled with "
                "PLAY, never a position. #446's read at thirty rows counts those rows too, labelled.")
RULING_223_5 = ("THE RECEIPT SCRIPT PR (#446, 209 item 3) — its two questions, ruled: (a) \"what was done\" prints what "
                "the LEDGER holds, under the ledger's own label for it (an operator fill prints as the ledger labels it; "
                "a would-be row with no ledger position stays blank); the script reports and never relabels. It prints "
                "NO quantity, price, fee or P&L for any row, so a pasted console cannot carry a fill size or let a "
                "reader infer the unit (209 item 3). (b) Results from the DB copy, as results-tally reads them, STAYS — "
                "opened mode=ro + immutable=1 (198 item 6(ii)), the header naming the copy and the closing-file "
                "directory as the two sources, a row whose game the copy lacks labelled \"no result in this copy\", "
                "never scored. It takes the slot #800 freed.")
RULING_225_3 = ("#804 (the QB-hold receipt) — its three questions: Q1 RULED by 2(a) above: a row the copy lacks (\"no "
                "result in this copy\"), a teams-differ row and a void row each COUNT toward thirty as labelled, "
                "unscored rows, kept outside the W-L-P with their label (the change local to collect(), as offered). "
                "Q2 CONFIRMED: \"what was done\" is the ledger's fills, never the Cockpit's claims (a claim is what the"
                " page said). Q3 CONFIRMED as built: a would-be row's price line reads \"none (PASS on the page)\"; its"
                " exec edge stays on the row. One push for Q1; CI green then my block. The count the script prints is"
                " the count; my \"about fifteen\" was a read of the pages, not a rule.")
KEYS = ("rows = the NFL closing files, one per game (exec_cohorts' rule: the newest run's row within the Desk's clock "
        "drift of the match's current start) · PLAY = desk.call PLAY with a QB tag (exec_cohorts.QB_TAGS) · would-be "
        "= desk.call PASS, pass_kind market_only, market_only_hold.would_call PLAY, with a QB tag · price named = a "
        "PLAY's desk.order.limit; a would-be row names none · close = close.grading_close_block's fair for the page's "
        "side · result = the database copy, as results-tally reads it (exec_cohorts.result_of) · unscored = a row the "
        "copy's checks leave out, labelled by its cause (a game the copy lacks: \"no result in this copy\"; teams "
        "differ; re-dated void), never scored, outside the W-L-P, and COUNTED toward thirty (225 item 3) · what was done = what the ledger holds on the game (by event "
        "ticker, else the Cockpit's game matcher), under its own label: fills, each entry's ticker, side, title, "
        "opened, closed as held; never a quantity, price, fee or P&L; none: not established; matched to the scored rows "
        "only · count toward thirty = "
        "each kind's scored rows + its unscored rows; the printed count is the count (225 item 3) · every count is "
        "per kind; only the count toward thirty adds the two")


class Refused(Exception):
    """A refusal: printed as REFUSED, exit 2."""


# ------------------------------------------------------------------------------------------------- the ledger --

def read_ledger(path) -> dict:
    """The Cockpit's ledger export, or Refused: not readable, not JSON, or not a bd_ledger_v1 export (no calls array;
    a call or a fill that is not an object; fills present and not an array; a fill's LEDGER_FIELDS value present and
    not a string: the field named, the value never echoed)."""
    try:
        with open(path) as fh:
            L = json.load(fh)
    except (OSError, ValueError) as e:
        raise Refused(f"--ledger {path}: cannot read the ledger export ({type(e).__name__}); nothing read") from None
    if not isinstance(L, dict) or not isinstance(L.get("calls"), list):
        raise Refused(f"--ledger {path}: not a bd_ledger_v1 export (no calls array); nothing read")
    if any(not isinstance(c, dict) for c in L["calls"]):
        raise Refused(f"--ledger {path}: a call is not an object; nothing read")
    fills = L.get("fills", [])
    if fills is None:
        fills = []
    if not isinstance(fills, list) or any(not isinstance(f, dict) for f in fills):
        raise Refused(f"--ledger {path}: fills is not an array of objects; nothing read")
    for f in fills:          # the printable fields are the export's strings or null; a figure there is never printed
        for k in LEDGER_FIELDS:
            if f.get(k) is not None and not isinstance(f[k], str):
                raise Refused(f"--ledger {path}: a fill's {k} is not a string or null (the value is not printed); "
                              "nothing read")
    return {"calls": L["calls"], "fills": fills}


def _event(ticker) -> str | None:
    t = str(ticker or "").strip().upper()
    return t.rsplit("-", 1)[0] if "-" in t else None


def _row_events(row: dict, desk: dict) -> set:
    """The Kalshi events the row names: its order's ticker and its legs' tickers (the market less its side)."""
    out = set()
    order = desk.get("order") if isinstance(desk.get("order"), dict) else {}
    legs = row.get("kalshi_legs") if isinstance(row.get("kalshi_legs"), dict) else {}
    for t in [order.get("ticker")] + [(v or {}).get("ticker") for v in legs.values() if isinstance(v, dict)]:
        e = _event(t)
        if e:
            out.add(e)
    return out


def positions(L: dict, rows: list[dict]) -> dict:
    """{row key: [{ticker, side, title, opened, closed}, ...] one per entry}: each fills entry on the row's game, its
    own field names and values as held (LEDGER_FIELDS; 223 item 5(a): never relabelled), "ambiguous": entries that fit
    more than one row, "nfl_fills": the NFL game entries read. Every entry stays its own (a split or partial fill whose
    printed fields match another's is still two entries); only the same entry (the same non-empty string id) is read
    once, and an entry with no id is never deduped. The id is read for that and printed nowhere. The matcher reads the
    ticker, side and title; nothing else of an entry is kept: no quantity, price, fee, P&L or id."""
    from src.walters import ledger_fills as lf
    found: dict = {}
    amb = nfl = 0
    seen: set = set()
    for f in L["fills"]:
        fid = f.get("id")
        if isinstance(fid, str) and fid:
            if fid in seen:
                continue
            seen.add(fid)
        fx = {**f, **lf.parse_ticker(f.get("ticker"))}
        if fx.get("kind") != "sport" or fx.get("family") != FAMILY:
            continue
        nfl += 1
        fx.update(lf.side_fields(fx, fx.get("title"), fx.get("side")))
        ev = _event(f.get("ticker"))
        cands = [r for r in rows if ev and ev in r["events"]]
        if not cands:
            near = [r for r in rows if lf.day_diff(r["kickoff_iso"][:10], fx.get("date")) <= 1
                    and lf.game_fits(fx, {"home": r["home"], "away": r["away"]})]
            cands = lf._start_nearest(fx, [{**r, "kickoff": r["kickoff_iso"]} for r in near])
        keys = list(dict.fromkeys(r["key"] for r in cands))
        if len(keys) > 1:
            amb += 1
            continue
        if not keys:
            continue
        found.setdefault(keys[0], []).append({k: f.get(k) for k in LEDGER_FIELDS})
    return {"by_row": found, "ambiguous": amb, "nfl_fills": nfl}


def done_text(ps: list[dict] | None, ledger_read: bool) -> str:
    """'what was done' (223 item 5(a)), the same rule for a PLAY row and a would-be row: what the ledger holds on the
    game, under its own label (LEDGER_LABEL, each entry's LEDGER_FIELDS as held, JSON), never relabelled; blank ("not
    established", 46 item 4) where it holds nothing; "not read (no --ledger)" without the file."""
    if not ledger_read:
        return NOT_READ
    if not ps:
        return NOT_ESTABLISHED
    return f"{LEDGER_LABEL}: " + "; ".join(json.dumps(p, ensure_ascii=False) for p in ps)


# --------------------------------------------------------------------------------------------------- the rows --

def classify(desk: dict) -> str | None:
    """"play", "would" or None (not a row of this receipt)."""
    from src.walters import desk_policy
    from src.walters.exec_cohorts import QB_TAGS
    tags = desk.get("tags") if isinstance(desk.get("tags"), list) else []
    if not {t for t in tags if isinstance(t, str)} & set(QB_TAGS):
        return None
    if desk.get("engine") != "model_edge":
        return None
    if desk.get("call") == "PLAY":
        return "play"
    hold = desk.get("market_only_hold") if isinstance(desk.get("market_only_hold"), dict) else {}
    if (desk.get("call") == "PASS" and desk.get("pass_kind") == desk_policy.NFL_MARKET_ONLY_KIND
            and hold.get("would_call") == "PLAY"):
        return "would"
    return None


def _num(x) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        return None
    return float(x)


def collect(s, exports_dir) -> dict:
    """The receipt's rows from the closing files and the database copy `s` (read-only; nothing written): "rows" (the
    scored rows), "unscored" (per kind, by cause, UNSCORED_HEADS: each named with its label, never scored, kept
    outside the W-L-P) and "toward_thirty" (per kind: its scored rows + its unscored rows; 225 item 3: a row the copy
    lacks, a teams-differ row and a void row each COUNT toward thirty as labelled, unscored rows)."""
    from src.db.schema import Match
    from src.walters.close import grading_close_block
    from src.walters.exec_cohorts import QB_TAGS, _within, result_of
    from src.walters.redated import as_utc, closing_rows, void_label

    cr = closing_rows(exports_dir)
    rows = []
    unscored = {k: {key: [] for key, _ in UNSCORED_HEADS} for k in ("play", "would")}
    nfl_matches = 0
    for mid in sorted(cr["rows"]):
        entries = cr["rows"][mid]
        m = s.get(Match, mid)
        lab = None
        if m is None:
            e = entries[-1]
        else:
            near = _within(entries, m.utc_date)
            if near:
                e = near[-1]
            else:
                lab = void_label([(run, r.get("utc_date")) for run, _, r in entries], m.utc_date)
                e = entries[-1]
        if e[1] != FAMILY:
            continue
        nfl_matches += 1
        row = e[2]
        desk = row.get("desk") if isinstance(row.get("desk"), dict) else {}
        kind = classify(desk)
        if kind is None:
            continue
        game = f"{row.get('away_team') or '?'} @ {row.get('home_team') or '?'}"
        tag = WOULD_LABEL if kind == "would" else "PLAY"
        if m is None:
            unscored[kind]["no_result"].append(f"match {mid} {game} ({tag})")
            continue
        h = m.home_team.name if m.home_team else None
        a = m.away_team.name if m.away_team else None
        if (row.get("home_team"), row.get("away_team")) != (h, a):
            unscored[kind]["teams"].append(f"match {mid} {game} ({tag}; this database's match {mid} is {a or '?'} @ "
                                       f"{h or '?'})")
            continue
        if lab:
            unscored[kind]["void"].append(f"match {mid} {game} ({tag}): {lab}")
            continue
        pick = desk.get("pick")
        hold = desk.get("market_only_hold") if isinstance(desk.get("market_only_hold"), dict) else {}
        reasons = hold.get("would_reasons") if kind == "would" else desk.get("reasons")
        reasons = [x for x in (reasons if isinstance(reasons, list) else [])
                   if isinstance(x, str) and x.startswith(QB_REASON_HEADS)]
        tags = [t for t in desk.get("tags") or [] if isinstance(t, str) and t in QB_TAGS]
        ex = desk.get("exec") if isinstance(desk.get("exec"), dict) else {}
        order = desk.get("order") if isinstance(desk.get("order"), dict) else {}
        cb = grading_close_block(s, m)
        fair = (cb.get("close_fair") or {}).get(pick) if pick in ("HOME", "AWAY") else None
        res = result_of(m, pick)
        ko = as_utc(m.utc_date)
        rows.append({
            "key": mid, "kind": kind, "match_id": mid, "home": h, "away": a, "pick": pick,
            "team": {"HOME": h, "AWAY": a}.get(pick), "kickoff_iso": ko.strftime("%Y-%m-%dT%H:%M:%S"),
            "kickoff_et": ko.replace(tzinfo=timezone.utc).astimezone(ET).strftime("%Y-%m-%d %H:%M ET"),
            "run": e[0], "tags": tags, "qb_reasons": reasons,
            "exec_edge_pp": _num(ex.get("edge_pp")), "market_ref": _num(desk.get("market_ref")),
            "limit": _num(order.get("limit")) if kind == "play" else None,
            "limit_basis": order.get("limit_basis") if kind == "play" else None,
            "close": _num(fair), "close_reference": cb.get("close_reference"), "close_books": cb.get("close_books"),
            "result": res, "score": (m.away_score, m.home_score), "events": _row_events(row, desk)})
    rows.sort(key=lambda r: (r["kickoff_iso"], r["match_id"]))
    toward = {k: sum(1 for r in rows if r["kind"] == k) + sum(len(v) for v in unscored[k].values())
              for k in ("play", "would")}
    return {"rows": rows, "unscored": unscored, "toward_thirty": toward, "files": cr["files"],
            "unreadable": cr["unreadable"], "runs": cr["runs"], "nfl_matches": nfl_matches}


# -------------------------------------------------------------------------------------------------- the lines --

RESULT_TEXT = {"win": "won", "loss": "lost", "push": "push", "void": "void", "open": "open (not final)"}


def _f(x, nd=2) -> str:
    return "—" if x is None else f"{x:.{nd}f}"


def row_line(r: dict, done: str) -> str:
    side = f"{r['pick'] or '-'}" + (f" ({r['team']})" if r["team"] else "")
    if r["kind"] == "play":
        said = f"PLAY {side}"
        price = (f"limit {_f(r['limit'])} ({r['limit_basis'] or 'basis not written'})" if r["limit"] is not None
                 else "no order price on the page")
    else:
        said = f"PASS (market-only, addendum 214); {WOULD_LABEL}: {side}"
        price = "none (PASS on the page)"
    qb = " · ".join(r["tags"]) + (f" — {'; '.join(r['qb_reasons'])}" if r["qb_reasons"] else "")
    edge = "exec edge —" if r["exec_edge_pp"] is None else f"exec edge {r['exec_edge_pp']:+.1f}pp"
    close = (f"close {_f(r['close'], 3)} ({r['close_reference'] or 'books'})" if r["close"] is not None
             else f"close unpriced (books {r['close_books'] or 0})")
    a, h = r["score"]
    score = f" {a}-{h} (away-home)" if r["result"] in ("win", "loss", "push") and a is not None else ""
    return (f"- {r['kickoff_et']} · {r['away']} @ {r['home']} [match {r['match_id']}] · page: {said} · QB: {qb} · "
            f"{edge} · market ref {_f(r['market_ref'], 3)} · price named: {price} · {close} · result: "
            f"{RESULT_TEXT[r['result']]}{score} · what was done: {done}")


def _graded(rs: list[dict]) -> dict:
    return {k: sum(1 for r in rs if r["result"] == k) for k in ("win", "loss", "push", "void", "open")}


def count_line(n_play: int, n_would: int, g_play: dict, g_would: dict, u_play: dict | None = None,
               u_would: dict | None = None) -> str:
    """The count toward thirty: n_play / n_would are each kind's count (its scored rows + its unscored rows, 225 item
    3); beside it each kind's record (g_*, the scored rows only) and its unscored rows by cause (u_*, {cause: n})."""
    total = n_play + n_would
    tail = (f"thirty reached — for the architect's read (no verdict is computed here)" if total >= READ_AT
            else "not read before thirty rows or the season's end (no verdict is computed here)")

    def rec(g, u):
        u = u or {}
        n = sum(u.get(key, 0) for key, _ in UNSCORED_HEADS)
        return (f"W-L-P {g['win']}-{g['loss']}-{g['push']}, void {g['void']}, open {g['open']}, unscored {n} ("
                + " · ".join(f"{head} {u.get(key, 0)}" for key, head in UNSCORED_HEADS) + ")")
    return (f"COUNT toward thirty (#446; addendum 44 item 9, 209 item 3; would-be rows counted too, labelled, 217 item "
            f"4; unscored rows counted too, labelled, outside the W-L-P, 225 item 3): PLAY {n_play} + {WOULD_LABEL} "
            f"{n_would} = {total} of {READ_AT} — {tail} · PLAY {rec(g_play, u_play)} · {WOULD_LABEL} "
            f"{rec(g_would, u_would)}")


def report(s, exports_dir, ledger: dict | None, db_text: str, ledger_text: str, echo=print) -> dict:
    from src.walters.redated import void_counts
    out = collect(s, exports_dir)
    rows = out["rows"]
    pos = positions(ledger, rows) if ledger is not None else {"by_row": {}, "ambiguous": 0, "nfl_fills": 0}
    d = str(exports_dir).rstrip("/")
    echo("QB-HOLD RECEIPT — every NFL row the Desk called PLAY with a QB flag or an unread list, and the would-be PLAY "
         "rows while NFL is uncertified (#446), read-only")
    echo(f"RULING (ARCHITECT 2026-10-12 08:41 ET, addendum 44 item 9, verbatim): \"{RULING_44_9}\"")
    echo(f"RULING (ARCHITECT 2026-11-02 08:30 ET, addendum 209 item 3, verbatim): \"{RULING_209_3}\"")
    echo(f"RULING (ARCHITECT 2026-11-02 11:20 ET, addendum 217 item 4, verbatim): \"{RULING_217_4}\"")
    echo(f"RULING (ARCHITECT 2026-11-02 18:05 ET, addendum 223 item 5, verbatim): \"{RULING_223_5}\"")
    echo(f"RULING (ARCHITECT 2026-11-03 07:55 ET, addendum 225 item 3, verbatim): \"{RULING_225_3}\"")
    runs = (f"runs {out['runs'][0]:%Y-%m-%d %H:%M}Z to {out['runs'][1]:%Y-%m-%d %H:%M}Z" if out["runs"] else "runs —")
    bad = (f" · unreadable {len(out['unreadable'])}: {', '.join(out['unreadable'])}" if out["unreadable"] else "")
    echo(f"SOURCES (the two, 223 item 5(b)): the copy {db_text} · the closing-file directory {d} (closing_*.json, "
         f"redated.closing_rows; host/ never read): {out['files']} read, {runs}, NFL games {out['nfl_matches']}{bad}")
    echo(f"WHAT WAS DONE FROM: {ledger_text}")
    echo(f"KEYS: {KEYS}")
    plays = [r for r in rows if r["kind"] == "play"]
    would = [r for r in rows if r["kind"] == "would"]
    ledger_read = ledger is not None
    for label, rs in ((PLAY_LABEL, plays), (WOULD_LABEL, would)):
        echo(f"{label} — {len(rs)} scored row{'s' if len(rs) != 1 else ''}, by kickoff")
        for r in rs:
            echo(row_line(r, done_text(pos["by_row"].get(r["key"]), ledger_read)))
    uo = out["unscored"]
    u_n = {k: {key: len(uo[k][key]) for key, _ in UNSCORED_HEADS} for k in ("play", "would")}
    def u_head(k, key, head):      # the void head carries redated's split: one void state, two labels (109 item 2 Q2)
        return f"{head} {u_n[k][key]}" + (f" ({void_counts(uo[k][key])})" if key == "void" else "")
    echo("UNSCORED (counted toward thirty, labelled, never scored, outside the W-L-P, 225 item 3; per kind, never "
         "pooled): " + "; ".join(f"{lab} — " + " · ".join(u_head(k, key, head) for key, head in UNSCORED_HEADS)
                                 for k, lab in (("play", "PLAY"), ("would", WOULD_LABEL))))
    for k in ("play", "would"):
        for key, head in UNSCORED_HEADS:
            for x in uo[k][key]:
                echo(f"  {head} (unscored, counted): {x}")
    held_play = sum(1 for r in plays if pos["by_row"].get(r["key"]))
    held_would = sum(1 for r in would if pos["by_row"].get(r["key"]))
    if ledger_read:
        echo(f"LEDGER: NFL game {LEDGER_LABEL} entries read {pos['nfl_fills']} · fitting more than one row (ambiguous, "
             f"given to none) {pos['ambiguous']} · PLAY scored rows with {LEDGER_LABEL} on the game {held_play} of "
             f"{len(plays)} · {WOULD_LABEL} scored rows with {LEDGER_LABEL} on the game {held_would} of {len(would)} "
             f"(an unscored row is not matched to {LEDGER_LABEL})")
    g_play, g_would = _graded(plays), _graded(would)
    tw = out["toward_thirty"]
    echo(count_line(tw["play"], tw["would"], g_play, g_would, u_n["play"], u_n["would"]))
    summary = {"exports": d, "closing_files": out["files"], "unreadable": len(out["unreadable"]),
               "nfl_games": out["nfl_matches"], "play_rows": len(plays), "would_be_rows": len(would),
               "counted": {"play": tw["play"], "would_be": tw["would"]},
               "toward_thirty": tw["play"] + tw["would"], "read_at": READ_AT,
               "thirty_reached": tw["play"] + tw["would"] >= READ_AT, "play_record": g_play,
               "would_be_record": g_would, "ledger_read": ledger_read,
               "what_was_done": ({"play": {LEDGER_LABEL: held_play, "not_established": len(plays) - held_play},
                                  "would_be": {LEDGER_LABEL: held_would, "not_established": len(would) - held_would}}
                                 if ledger_read else None),
               "ambiguous_fills": pos["ambiguous"] if ledger_read else None,
               "unscored": {"play": u_n["play"], "would_be": u_n["would"]}}
    echo("QB-HOLD-RECEIPT " + json.dumps(summary, sort_keys=True))
    return {**out, "positions": pos, "summary": summary}


# ------------------------------------------------------------------------------------------------------- main --

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="#446 (addendum 44 item 9; 209 item 3; 217 item 4): the QB hold, measured "
                                             "— read-only")
    ap.add_argument("--db", default=None, help="a .backup copy of the database outside the repo's data/, opened "
                                               "mode=ro&immutable=1 (required)")
    ap.add_argument("--exports", default="exports", help="the exports directory holding closing_*.json "
                                                         "(default exports; host/ is never read: a directory "
                                                         "named host in any case, a symlink so named, or a "
                                                         "symlink to one, is refused)")
    ap.add_argument("--ledger", default=None, help="the Cockpit's Export ledger (JSON) file, bd_ledger_v1_<date>.json "
                                                   "(optional: without it 'what was done' reads not read)")
    a = ap.parse_args(argv)
    from src.walters import mlb_pitchers_gate as mp
    try:
        path = mp.check_db(a.db)
        for sc in SIDECARS:
            if path.with_name(path.name + sc).exists():
                raise mp.GateRefused(f"--db {a.db} has a {sc} sidecar ({path.name + sc}): not a fresh .backup copy; "
                                     "immutable=1 would ignore it and read a stale file; take a fresh .backup copy")
        if not Path(a.exports).is_dir():
            raise Refused(f"--exports {a.exports}: not a directory; nothing read")
        # by its own name or its target's, in any case (a Mac's default volume ignores case: HOST/ is host/)
        if "host" in {Path(os.path.abspath(a.exports)).name.lower(), Path(a.exports).resolve().name.lower()}:
            raise Refused(f"--exports {a.exports}: names or resolves to a host/ directory ({Path(a.exports).resolve()}); "
                          "host/ is never read, its files carry the host's match ids; nothing read")
        ledger = read_ledger(a.ledger) if a.ledger else None
        mp.open_ro(path).close()
    except (mp.GateRefused, Refused) as err:
        print(f"REFUSED: {err}" + ("" if str(err).endswith("nothing read") else "; nothing read"))
        return REFUSED
    import sqlite3

    from sqlalchemy.exc import SQLAlchemyError
    db_text = (f"--db {path} (a .backup copy, opened {mp.COPY_URI_QUERY.lstrip('?')}; the results, as results-tally "
               "reads them: exec_cohorts.result_of)")
    ledger_text = (f"ledger {a.ledger} (bd_ledger_v1: calls {len(ledger['calls'])}, fills {len(ledger['fills'])})"
                   if ledger is not None else "ledger not read (no --ledger): 'what was done' reads not read")
    lines: list[str] = []
    try:
        with mp.readonly_session(path) as s:
            report(s, a.exports, ledger, db_text, ledger_text, echo=lines.append)
    except (SQLAlchemyError, sqlite3.Error, LookupError) as err:   # a copy without the schema the read needs
        why = (str(err).strip().splitlines() or [""])[0]
        print(f"REFUSED: --db {path}: cannot be read as the schema the receipt needs ({type(err).__name__}: {why}); "
              "nothing read")
        return REFUSED
    for ln in lines:
        print(ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
