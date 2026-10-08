"""VENUE-EDGE: QUOTE AGE receipts (ARCHITECT 2026-10-07, addendum 4 E, gate-class) — READ-ONLY.

Build steps (3) and (4): "(3) A receipt over every VENUE call on file since 2026-10-02: the consensus at the call
and at each later pre-kickoff capture, and whether it ever moved. (4) Report, do not change: how old the book
quotes behind MODEL-sport references are at decision time (MLB, NFL, PL). That is the next ruling."

ON FILE = every JSON under the exports directory (recursive, so exports/host/ — the host's pulled copies — is
read too) that carries `desk_meta` (written with --desk), plus the Cockpit's ledger export when given. Fixtures
files are named per competition per UTC date (fixtures_<CODE>_<date>.json) and each run overwrites the day's file,
so only the LAST desk run of each day per machine is on file; earlier runs are not recoverable from exports/.

MATCH IDENTITY (Codex on #340): an export row's match_id is MACHINE-LOCAL (docs/specs/hosting-h1.md: the comparator
keys on (kickoff, home, away), never match_id). A row from a MIRRORED file (a path under <exports>/host/) is resolved
by stable identity only: exact home/away team names + kickoff within ±12h. A row from the laptop's own files uses its
match_id only after the DB row's teams and kickoff are verified against the exported home/away/utc_date; on a
mismatch it falls back to identity. Ambiguous or none -> unresolved, reported, never guessed.

THE CONSENSUS = a BOOK capture session in odds_snapshots: one (source, captured_at) stamp, market 1X2, every
outcome of the sport present (two-way HOME/AWAY; soccer HOME/DRAW/AWAY), source != "kalshi"; fair = devig_prob
normalised over the outcomes (src/walters/close.close_from_snapshots' rule); books = max n_books. "MOVED" = any
outcome's fair differs at FOUR DECIMALS (round(p, 4)) from the anchor's. Captures are OUR fetch times: a
consensus that does not move across fetches is the staleness signal; no quote time is stored (the provider's
own quote time is the probe's question, scripts/odds_payload_probe.py).

Nothing here writes: SELECTs only. Percentiles are nearest-rank on the sorted list, index round(q·(n−1)).
"""
from __future__ import annotations

import contextlib
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone

SINCE_DEFAULT = datetime(2026, 10, 2)            # naive UTC: "every VENUE call on file since 2026-10-02"
DP = 4                                           # "unchanged to four decimals"
MODEL_SPORTS = ("MLB", "NFL", "PL")              # build step (4): the live model sports
#: Desk export filenames (fixtures_<comp>_*, <sport>_predictions_*, desk_parlays_*, window_*): an unreadable file
#: with such a name is a damaged export; since --out allows any name, EVERY unreadable JSON refuses the receipt.
#: export-predictions' default name: <sport>[_<COMP>]_<YYYY-MM-DD>[_to_<YYYY-MM-DD>].json (rows key: predictions)
#: A competition code may carry underscores (UEFA_EURO, WCQ_EU, CNL_Q; Codex on #340); a results export
#: (<sport>[_<COMP>]_results_<date>.json) is not a prediction export.
DEFAULT_PRED_NAME = re.compile(r"^(soccer|nfl|mlb|nhl)(?:_(?!results_\d{4}-)[A-Za-z0-9]+)*"
                               r"_\d{4}-\d{2}-\d{2}(_to_\d{4}-\d{2}-\d{2})?\.json$", re.I)
EXPORT_NAME = re.compile(r"^(fixtures_|desk_parlays_|window_)|predictions|" + DEFAULT_PRED_NAME.pattern, re.I)
SPREAD_SPORTS = ("NFL", "NCAA", "NCAAF")
#: the export families a document-level `sport` may name (schema Sport values + the shadow / intl families)
#: the competitions a single-league export family carries (src/db/schema.py Sport: NCAA football is Sport.NFL;
#: the shadow families name their own league). soccer / unl / intl carry open competition sets: not checked here
FAMILY_COMPETITIONS = {"nfl": {"NFL", "NCAA", "NCAAF"}, "mlb": {"MLB"}, "nhl": {"NHL"}, "ncaa": {"NCAA", "NCAAF"}}
KNOWN_SPORTS = ("soccer", "nfl", "mlb", "nhl", "ncaa", "unl", "intl")          # sports whose reference can be spread_derived
#: tools/cockpit.html's ledger writers: engine:"model_edge" (straight / ladder / shadows / parlay legs) and
#: engine:"venue_edge"; no other value has ever been written (since 76edfa3, the ledger's first version)
LEDGER_ENGINES = ("model_edge", "venue_edge")
LEDGER_CLAIM_SOURCES = (None, "auto")          # tools/cockpit.html snapshotCalls: c.claim_source="auto"; manual: absent
LEDGER_UNKNOWN_SOURCE = "unknown (the ledger keeps no fair_source)"
MIRROR_DIR = "host"                              # <exports>/host/: deploy/hosting/pull_exports.py's destination
WINDOW = timedelta(hours=12)                     # identity match: exact team names, kickoff within ±12h
PROXY_LABEL = ("capture-based PROXIES (our fetch times), NOT quote age: no quote time is stored; the provider "
               "can serve an old quote on a fresh fetch (ARCHITECT 2026-10-07)")


# ------------------------------------------------------------------ parsing --

def parse_ts(v) -> datetime | None:
    """ISO text -> naive UTC (the DB's convention); naive input is UTC (#178). None / unparseable -> None."""
    if not v or not isinstance(v, str):
        return None
    s = v.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo is not None else dt


class Refused(Exception):
    """A receipt input that cannot be read as asked: refused with its reason (exit 2), never reported as empty."""


def ledger_refusal(L) -> str | None:
    """A Cockpit ledger export the receipt can audit: an object with a calls array whose EVERY entry is an object
    (Codex on #340, as k-track-receipt checks). A damaged entry refuses the receipt: skipping it would understate
    the claims while reading as complete."""
    if not isinstance(L, dict) or not isinstance(L.get("calls"), list):
        return "REFUSED: not a Cockpit ledger export (no calls array)."
    bad = [i for i, c in enumerate(L["calls"]) if not isinstance(c, dict)]
    if not bad:
        # Codex on #340: a venue claim's reprices[] decides whether it was re-logged (frozen vs latest prices) and
        # its re-log count; a damaged array is refused, never filtered down to what survives
        for i, c in enumerate(L["calls"]):
            if c.get("engine") not in LEDGER_ENGINES:
                # Codex on #340: the Cockpit writes model_edge / venue_edge only; a damaged discriminator is
                # never read as "not a venue claim" and dropped
                return (f"REFUSED: ledger call at index {i} has an unknown engine {c.get('engine')!r} (the Cockpit "
                        f"writes {' / '.join(LEDGER_ENGINES)}): a damaged claim is never filtered out silently.")
            if c.get("engine") != "venue_edge":
                continue
            bad_num = [k for k in ("model_p", "market_p", "kalshi_p", "divergence_pp", "units", "claim_model_p",
                                   "claim_market_p", "claim_exec_cost") if not _num(c.get(k))]
            if bad_num:                                # Codex on #340: formatted / compared as numbers
                return (f"REFUSED: venue claim at index {i} has non-numeric {', '.join(bad_num)}: its prices "
                        "cannot be audited.")
            bad_str = [k for k in ("sport", "home", "away", "kickoff", "pick", "claim_source") if not _str(c.get(k))]
            if not bad_str and c.get("claim_source") not in LEDGER_CLAIM_SOURCES:
                # Codex on #340: the Cockpit writes claim_source "auto" (snapshotCalls) or none (a manual claim); any
                # other value would take the manual merge path silently
                return (f"REFUSED: venue claim at index {i} has an unknown claim_source {c.get('claim_source')!r} (the "
                        "Cockpit writes \"auto\" or none): its merge path cannot be audited.")
            if bad_str:                                # Codex on #340: hashed into merge keys, never a TypeError
                return (f"REFUSED: venue claim at index {i} has non-string {', '.join(bad_str)}: its identity "
                        "cannot be audited.")
            if c.get("kickoff") not in (None, "") and parse_ts(c.get("kickoff")) is None:
                # Codex on #340: an unparseable kickoff never merges with its file call or resolves to the DB: it
                # would count twice (the file call + a NO DB MATCH ledger row)
                return (f"REFUSED: venue claim at index {i} has an unparseable kickoff {c.get('kickoff')!r}: its "
                        "identity cannot be audited.")
            if c.get("claim_at") not in (None, "") and parse_ts(c.get("claim_at")) is None:
                return (f"REFUSED: venue claim at index {i} has an unparseable claim_at {c.get('claim_at')!r}: the "
                        "frozen claim time is damaged, never replaced by the mutable claim_as_of / captured_at.")
            if c.get("claim_at") in (None, ""):        # Codex on #340: a legacy claim's fallback times, validated
                for f in ("claim_as_of", "captured_at"):
                    if c.get(f) not in (None, "") and parse_ts(c.get(f)) is None:
                        return (f"REFUSED: legacy venue claim at index {i} has an unparseable {f} {c.get(f)!r}: its "
                                "claim time cannot be audited.")
                if parse_ts(c.get("claim_as_of")) is None and parse_ts(c.get("captured_at")) is None:
                    return (f"REFUSED: venue claim at index {i} has no claim time at all (no claim_at, claim_as_of or "
                            "captured_at): it would be omitted silently.")
            if "reprices" not in c:
                continue
            rp = c["reprices"]
            if not isinstance(rp, list) or any(not isinstance(r, dict) or parse_ts(r.get("at")) is None for r in rp):
                return (f"REFUSED: venue claim at index {i} has a damaged reprices array (not a list of objects "
                        "with a parseable 'at'): its re-logs and claim prices cannot be audited.")
            t0 = parse_ts(c.get("claim_at"))
            if t0 is not None and any(parse_ts(r["at"]) < t0 for r in rp):
                return (f"REFUSED: venue claim at index {i} has a re-log before its frozen claim_at: a "
                        "chronologically damaged position, never counted as a later re-log.")
    if bad:
        return (f"REFUSED: the ledger's calls array has {len(bad)} non-object entr{'y' if len(bad) == 1 else 'ies'} "
                f"(index {', '.join(map(str, bad[:5]))}{', …' if len(bad) > 5 else ''}): a damaged ledger, "
                "never audited as complete.")
    return None


def market_ok(mk) -> bool:
    """A row's market block, if present, is an object; its fair_prob, if present, an object of numeric (or null)
    probabilities (Codex on #340: a damaged fair is refused at discovery, never a traceback while rounding)."""
    if mk is None:
        return True
    if not isinstance(mk, dict):
        return False
    sel = mk.get("selections")                 # the alternate market shape (Codex on #340)
    if sel is not None and not (isinstance(sel, dict) and all(
            v is None or (isinstance(v, dict) and _num(v.get("fair_prob"))) for v in sel.values())):
        return False
    if not _num(mk.get("bookmaker_count")) or any(not (mk.get(k) is None or isinstance(mk.get(k), str))
                                                   for k in ("captured_at", "fair_source")):
        return False                           # hashed into call signatures (Codex on #340)
    fp = mk.get("fair_prob")
    if fp is None:
        return True
    return isinstance(fp, dict) and all(_num(v) for v in fp.values())


def _num(v) -> bool:
    """numeric or null (a bool is not a number; NaN / Infinity, which json.load accepts, are not either: Codex
    on #340, a NaN anchor compares false and would read as verified)"""
    return v is None or (isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v))


def _str(v) -> bool:
    return v is None or isinstance(v, str)


DESK_CALLS = {"model_edge": {"PLAY", "PASS", "LADDER"}, "venue_edge": {"VENUE", "PASS"}}   # desk_policy's own
DESK_REFERENCES = {None, "books", "kalshi_only"}
#: desk_policy.desk_block: a VENUE block carries no reference; a model PLAY / LADDER always has one (its edge needs
#: mkt_ref); only a model PASS may lack it (noref) (Codex on #340: the combination, not just each vocabulary)
_REF_ALLOWED = {("venue_edge", c): {None} for c in DESK_CALLS["venue_edge"]}
_REF_ALLOWED.update({("model_edge", "PLAY"): {"books", "kalshi_only"}, ("model_edge", "LADDER"): {"books", "kalshi_only"},
                     ("model_edge", "PASS"): DESK_REFERENCES})


def desk_ok(d) -> bool:
    """A desk block's identity fields are strings or null, and a VENUE block's numeric fields numeric or null
    (Codex on #340: they are hashed into call keys and formatted; never a traceback)."""
    if not isinstance(d, dict):
        return True
    if not all(_str(d.get(k)) for k in ("engine", "call", "side", "reference", "pass_kind")):
        return False
    # Codex on #340: the discriminators are desk_policy's own vocabulary; a corrupted value is a damaged block
    if d and (d.get("engine") not in DESK_CALLS or d.get("call") not in DESK_CALLS[d["engine"]]
              or d.get("reference") not in _REF_ALLOWED[(d["engine"], d["call"])]):
        return False
    if d.get("engine") != "venue_edge":
        return True
    return all(_num(d.get(k)) for k in ("book_p", "kalshi_p", "div_pp", "units")) and (
        d.get("stale_book_zone") is None or isinstance(d.get("stale_book_zone"), bool))


def desk_rows_ok(doc: dict) -> bool:
    """Every row the Desk annotates (desk_policy.normalize: a scheduled / status-less fixtures row when the doc has
    no predictions; a predictions row with a probability) carries a desk object (Codex on #340)."""
    if doc.get("engine") == "model_shadow":
        return True
    for k in ("fixtures", "predictions"):      # Codex on #340: a scalar container is damaged, never iterated
        if doc.get(k) is not None and not isinstance(doc[k], list):
            return False
    if isinstance(doc.get("fixtures"), list) and isinstance(doc.get("predictions"), list):
        return False                           # Codex on #340: no export writes both row families; a mixed document
                                               # would skip the fixture rows' desk check
    if doc.get("predictions") is None and isinstance(doc.get("fixtures"), list):
        rows = [f for f in doc["fixtures"] if isinstance(f, dict)
                and not (f.get("status") and f.get("status") != "scheduled")]
    else:
        rows = []
        for x in doc.get("predictions") or []:
            pr = x.get("prediction") if isinstance(x, dict) else None
            if pr is not None and not isinstance(pr, dict):
                return False                   # Codex on #340: a damaged prediction is never read as "no probability"
            pr = pr or {}
            if pr.get("probabilities") is not None or pr.get("home_win_prob") is not None:
                rows.append(x)
    # Codex on #340: the block's identity (engine, call) must be there: an empty {} is a damaged block
    return all(isinstance(x.get("desk"), dict) and isinstance(x["desk"].get("engine"), str)
               and isinstance(x["desk"].get("call"), str) for x in rows)


def doc_ident_ok(doc: dict) -> bool:
    """A desk document's sport metadata (sport / competition_code / competition) is string-or-null, and every
    fixtures / predictions row resolves to a sport: its own competition, else the document's (Codex on #340: damaged
    metadata must not read as an out-of-scope sport and drop every row silently)."""
    if not all(_str(doc.get(k)) for k in ("sport", "competition_code", "competition")):
        return False
    top = doc.get("competition_code") or doc.get("competition") or doc.get("sport")
    rows = [x for k in ("fixtures", "predictions") if isinstance(doc.get(k), list) for x in doc[k]]
    # Codex on #340: where the document's `sport` is the rows' only sport source, it must be a known family
    # (a typo such as "NFA" would read as out of scope and drop every row)
    only_sport = not (doc.get("competition_code") or doc.get("competition"))
    if only_sport and doc.get("sport") and str(doc["sport"]).lower() not in KNOWN_SPORTS and any(
            not (isinstance(x, dict) and x.get("competition")) for x in rows):
        return False
    # Codex on #340: a competition that contradicts the document's own single-league sport (nfl + "NFA") would
    # resolve the rows out of scope and drop them; the export's Sport enum fixes which codes each family carries
    fam = FAMILY_COMPETITIONS.get(str(doc.get("sport") or "").lower())
    if fam is not None:
        for x in rows:
            comp = (x.get("competition") if isinstance(x, dict) else None) or doc.get("competition_code") or \
                doc.get("competition")
            if comp and str(comp).upper() not in fam:
                return False
        if not rows and (doc.get("competition_code") or doc.get("competition")) and str(
                doc.get("competition_code") or doc.get("competition")).upper() not in fam:
            return False
    # Codex on #340: export.py filters a document to its competition_code (Competition.code ==), so a row naming
    # another competition is damaged, whatever the family (soccer included)
    code = doc.get("competition_code")
    if code and any(isinstance(x, dict) and x.get("competition") and str(x["competition"]).upper() != str(code).upper()
                    for x in rows):
        return False
    return bool(top) or all(isinstance(x, dict) and x.get("competition") for x in rows)


def venue_prices_ok(doc: dict) -> bool:
    """Every VENUE call's side is an outcome of its row's market.fair_prob and its book_p is that fair (desk_policy
    venue_edge: bookP = fair[side], from the same block) (Codex on #340: a contradicting copy never anchors)."""
    for x in doc.get("fixtures") or []:
        d = x.get("desk") if isinstance(x, dict) else None
        if not (isinstance(d, dict) and d.get("engine") == "venue_edge" and d.get("call") == "VENUE"):
            continue
        fp = (x.get("market") or {}).get("fair_prob") if isinstance(x.get("market"), dict) else None
        side = d.get("side")
        if not isinstance(fp, dict) or side not in fp or fp[side] is None or d.get("book_p") is None:
            return False
        if not (_num(d["book_p"]) and _num(fp[side])):
            return False                           # Codex on #340: validated before the arithmetic, never a TypeError
        if abs(d["book_p"] - fp[side]) >= 5e-4:
            return False
    return True


def row_ident_ok(x: dict) -> bool:
    """A row's identity fields (team names, kickoff, competition) are strings or null and its match_id an integer
    or null: they key calls and rows, and resolve the DB match."""
    mid = x.get("match_id")                    # Codex on #340: a DB primary key, passed to Session.get()
    return all(_str(x.get(k)) for k in ("home_team", "away_team", "utc_date", "competition")) and (
        mid is None or (isinstance(mid, int) and not isinstance(mid, bool)))


def db_file_path():
    """The configured SQLite DB file, resolved (None for a non-SQLite URL): what an --out must never alias."""
    from pathlib import Path

    from config import settings
    url = settings.database_url
    return Path(url[len("sqlite:///"):]).resolve() if url.startswith("sqlite:///") else None


@contextlib.contextmanager
def readonly_session():
    """A READ-ONLY session for the receipts (Codex on #340): the app's session_scope() commits on exit and its
    connect hook creates the DB directory and sets PRAGMA journal_mode=WAL. Here the SQLite file is opened with a
    mode=ro URI (no hook, no pragma, no commit); a missing DB file or a non-SQLite URL is refused, never created."""
    from pathlib import Path

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from config import settings
    url = settings.database_url
    if not url.startswith("sqlite:///"):
        raise Refused(f"REFUSED: the receipts read a SQLite DATABASE_URL only (got {url.split(':', 1)[0]})")
    path = db_file_path()
    if not path.is_file():
        raise Refused(f"REFUSED: no DB file at {path}: a read-only receipt never creates one")
    # mode=ro, never immutable (Codex on #340): an immutable open skips SQLite's change detection, so a write or a
    # checkpoint by the app during the receipt could be missed or read torn. A WAL database's reader may have SQLite
    # create its own -wal / -shm sidecars (as every reader, the app included, does); the database CONTENT is never
    # written: no hook, no pragma, no commit.
    eng = create_engine(f"sqlite:///file:{path.as_posix()}?mode=ro&uri=true",
                        connect_args={"uri": True, "check_same_thread": False})
    s = Session(eng)
    try:
        yield s
    finally:
        s.rollback()
        s.close()
        eng.dispose()


def iter_desk_docs(root: str) -> tuple[list[tuple[str, dict]], dict]:
    """Every JSON under `root` (recursive) whose top level carries desk_meta.as_of. Returns (docs, counts);
    counts["mirrored"] = the desk files under <root>/host/ (the host's pulled copies: foreign match_ids)."""
    docs, counts = [], {"json_files": 0, "unreadable": 0, "desk_files": 0, "mirrored": [], "other_files": 0}
    if not os.path.isdir(root):        # Codex on #340: a path error is never an empty audit
        raise Refused(f"REFUSED: --exports-dir {root!r} is not a directory (missing, misspelled or a file): "
                      "no receipt, never an empty one")
    bad_asof: list[str] = []
    bad_read: list[str] = []
    bad_rows: list[str] = []
    # Codex on #340: --exports-dir exports/host IS the mirror; every file under it is a host export
    root_is_mirror = os.path.basename(os.path.normpath(os.path.abspath(root))) == MIRROR_DIR
    walk_errors: list[str] = []
    for d, _, files in sorted(os.walk(root, onerror=lambda e: walk_errors.append(f"{e.filename}: {e.strerror}"))):
        for n in sorted(files):
            p = os.path.join(d, n)
            if not n.lower().endswith(".json"):        # Codex on #340: .JSON is JSON too
                # Codex on #340: `--out` takes any name (exports/audit, audit.txt); any other file that parses as a
                # desk document is read like any export, and anything else is counted, not read
                sniffed, text = None, ""
                try:
                    with open(p) as f:
                        text = f.read()
                    sniffed = json.loads(text)
                except (OSError, ValueError, UnicodeDecodeError):
                    sniffed = None
                    if text.lstrip().startswith("{"):
                        # Codex on #340: a file that begins as a JSON object but does not parse is a damaged export
                        # whatever its name (a truncated `--out exports/audit.txt`), never an unrelated file
                        counts["json_files"] += 1
                        counts["unreadable"] += 1
                        bad_read.append(p)
                        continue
                if not (isinstance(sniffed, dict) and "desk_meta" in sniffed):
                    counts["other_files"] = counts.get("other_files", 0) + 1
                    continue
            counts["json_files"] += 1
            try:
                with open(p) as f:
                    doc = json.load(f)
            except (OSError, ValueError, UnicodeDecodeError):
                counts["unreadable"] += 1
                # Codex on #340: a damaged EXPORT is never omitted silently: by its name, or (any --out name) by
                # the desk blocks its readable text still carries
                # Codex on #340: an export may carry any --out name and break before any marker (empty, early
                # truncation), so EVERY unreadable JSON under the exports dir refuses the receipt
                bad_read.append(p)
                continue
            if not isinstance(doc, dict):
                # Codex on #340: a generated export that parses as anything but an object is damaged; any name
                # (--out) that parses as null / a scalar / [] is too. A non-empty list is another file kind
                if EXPORT_NAME.search(n) or not (isinstance(doc, list) and doc):
                    bad_read.append(p)
                continue
            if not doc or EXPORT_NAME.search(n) and "desk_meta" not in doc and not any(
                    k in doc for k in ("fixtures", "predictions", "tickets", "results")):
                bad_read.append(p)          # Codex on #340: {} under ANY name (--out allows any), or a generated
                continue                    # export stripped of its metadata and rows, is damaged, never skipped
            if "desk_meta" not in doc and any(
                    isinstance(x, dict) and isinstance(x.get("desk"), dict)    # Codex on #340: even desk: {}
                    for k in ("fixtures", "predictions") if isinstance(doc.get(k), list) for x in doc[k]):
                bad_asof.append(p)                         # Codex on #340: Desk rows without desk_meta are damaged
                continue
            if "desk_meta" in doc:
                dm = doc["desk_meta"]                      # Codex on #340: every doc carrying desk_meta is
                if not isinstance(dm, dict) or parse_ts(dm.get("as_of")) is None:   # checked; missing = refused
                    bad_asof.append(p)
                    continue
                need = ("fixtures" if n.startswith("fixtures_") else
                        "predictions" if "predictions" in n.lower() or DEFAULT_PRED_NAME.search(n) else None)
                if need and need not in doc:               # Codex on #340: a named export lacking its rows
                    bad_rows.append(p)
                    continue
                if not desk_rows_ok(doc):
                    bad_rows.append(p)                     # Codex on #340: a row the Desk annotates lost its
                    continue                               # desk block: never read as a non-call
                if not doc_ident_ok(doc):
                    bad_rows.append(p)                     # Codex on #340: damaged sport metadata, never a
                    continue                               # silently out-of-scope document
                if not venue_prices_ok(doc):
                    bad_rows.append(p)                     # Codex on #340: a VENUE price contradicting its fair
                    continue
                if not any(k in doc for k in ("fixtures", "predictions", "tickets")):
                    bad_rows.append(p)                     # Codex on #340: any --out name; a desk doc with no
                    continue                               # rows container is damaged, never an empty file
                if any(k in doc and not isinstance(doc[k], list) for k in ("fixtures", "predictions")):
                    bad_rows.append(p)                             # Codex on #340: a container that is no list
                    continue
                rows = [x for k in ("fixtures", "predictions") if isinstance(doc.get(k), list) for x in doc[k]]
                if any(not isinstance(x, dict) or ("desk" in x and x["desk"] is not None
                                                   and not isinstance(x["desk"], dict))
                       or not market_ok(x.get("market")) or not desk_ok(x.get("desk"))
                       or not row_ident_ok(x) for x in rows):
                    bad_rows.append(p)
                    continue
                docs.append((p, doc))
                counts["desk_files"] += 1
                if root_is_mirror or os.path.relpath(p, root).split(os.sep)[0] == MIRROR_DIR:
                    counts["mirrored"].append(p)
    if walk_errors:                    # Codex on #340: an unreadable subtree is never an empty one
        raise Refused(f"REFUSED: {len(walk_errors)} director(y/ies) under --exports-dir could not be scanned "
                      f"({'; '.join(walk_errors[:5])}{'; …' if len(walk_errors) > 5 else ''}): their calls would be "
                      "omitted, so no receipt; fix the permissions, then re-run")
    if bad_read:
        raise Refused(f"REFUSED: {len(bad_read)} export file(s) that cannot be read as JSON "
                      f"({', '.join(bad_read[:5])}{', …' if len(bad_read) > 5 else ''}): truncated or unavailable; "
                      "their calls would be omitted, so no receipt; fix or move them, then re-run")
    if bad_rows:
        raise Refused(f"REFUSED: {len(bad_rows)} desk export(s) with a fixtures / predictions value that is not a list of "
                      f"objects (a missing one in a fixtures_* / *predictions* export or in any desk document, a row whose desk block is not an "
                      f"object, a malformed market / fair_prob / selections, a non-numeric VENUE field, or a non-string identity "
                      f"field / non-integer match_id, missing / non-string sport metadata, or a Desk-annotated row with no desk "
                      f"block) "
                      f"({', '.join(bad_rows[:5])}{', …' if len(bad_rows) > 5 else ''}): a damaged export is never "
                      "audited as complete; fix or move it, then re-run")
    if bad_asof:
        raise Refused(f"REFUSED: {len(bad_asof)} desk export(s) with an unparseable desk_meta.as_of (or Desk rows with "
                      f"no desk_meta at all) "
                      f"({', '.join(bad_asof[:5])}{', …' if len(bad_asof) > 5 else ''}): a damaged export is never "
                      "skipped silently; fix or move it, then re-run")
    return docs, counts


def same_fair(file_fair: dict | None, session_fair4: dict | None) -> bool:
    """The file's fair IS the session's: the SAME outcome set (a partial file fair never verifies, Codex on #340)
    and every outcome equal at 4dp."""
    return bool(file_fair and session_fair4 and set(file_fair) == set(session_fair4)
                and all(session_fair4[k] == v for k, v in file_fair.items()))


def _r4(fair: dict | None) -> dict | None:
    return None if not fair else {k: round(float(v), DP) for k, v in fair.items() if v is not None}


# ------------------------------------------------------------- the calls --

def _sec(t: datetime | None) -> datetime | None:
    return None if t is None else t.replace(microsecond=0)


def file_venue_calls(docs, since: datetime, mirrored=()) -> list[dict]:
    """Every fixtures row whose desk call is VENUE (engine venue_edge) at a desk as_of >= since. One call per
    (sport, home, away, kickoff, as_of, side) — stable identity, never the machine-local match_id: the same run
    found in two files (a copy) is one call with both paths. `match_id` is kept only from a LOCAL (non-mirrored)
    file, as a candidate that resolve_match verifies; a mirrored file's id is recorded as foreign, never used."""
    mirrored = set(mirrored or ())
    by_key: dict = {}
    for path, doc in docs:
        if not isinstance(doc.get("fixtures"), list):
            continue
        as_of = parse_ts(doc["desk_meta"].get("as_of"))
        if as_of is None or as_of < since:
            continue
        doc_sport = doc.get("competition_code") or doc.get("competition") or doc.get("sport")
        for f in doc["fixtures"]:
            # Codex on #340: the row's own competition first (doc_ident_ok accepts rows that name it themselves)
            sport = str((f or {}).get("competition") or doc_sport or "?").upper()
            d = (f or {}).get("desk") or {}
            if d.get("engine") != "venue_edge" or d.get("call") != "VENUE":
                continue
            mk = f.get("market") or {}
            foreign = path in mirrored
            kick = parse_ts(f.get("utc_date"))
            ident = (sport, f.get("home_team"), f.get("away_team"), kick, as_of, d.get("side"))
            # Codex on #340: two files are COPIES of one call only when the call-defining market numbers agree too
            # (fair at 4dp, capture time, books, book / Kalshi p, div); otherwise each is its own call, both flagged.
            fair4 = _r4(mk.get("fair_prob"))
            sig = (tuple(sorted((fair4 or {}).items())), mk.get("captured_at"), mk.get("bookmaker_count"),
                   d.get("book_p"), d.get("kalshi_p"), d.get("div_pp"), mk.get("fair_source"))   # + source (Codex)
            key = ident + (sig,)
            twins = [c for k, c in by_key.items() if k[:6] == ident and k != key]
            if twins and key not in by_key:
                for c in twins:
                    c["conflicting_copies"] = True
            if key in by_key:
                c = by_key[key]
                c["files"].append(path)
                if c.get("stale_book_zone") != d.get("stale_book_zone"):
                    # Codex on #340: copies that disagree on the Desk's stale flag keep both readings, never one
                    c["stale_book_zone_conflict"] = sorted({repr(c.get("stale_book_zone")),
                                                            repr(d.get("stale_book_zone"))}
                                                           | set(c.get("stale_book_zone_conflict") or []))
                if not foreign:
                    c["host_only"] = False
                if foreign:
                    c["foreign_ids"].append(f.get("match_id"))
                elif c["match_id"] is None:
                    c["match_id"] = f.get("match_id")
                continue
            by_key[key] = {
                "origin": "file", "files": [path], "in_ledger": False, "as_of": as_of, "sport": sport,
                "match_id": None if foreign else f.get("match_id"),
                "foreign_ids": [f.get("match_id")] if foreign else [], "reprices": [], "claim_basis": None,
                "home": f.get("home_team"), "away": f.get("away_team"),
                "kickoff": kick, "side": d.get("side"), "units": d.get("units"),
                "div_pp": d.get("div_pp"), "book_p": d.get("book_p"), "kalshi_p": d.get("kalshi_p"),
                "file_fair": _r4(mk.get("fair_prob")), "file_books": mk.get("bookmaker_count"),
                "file_captured_at": parse_ts(mk.get("captured_at")), "fair_source": mk.get("fair_source"),
                # ARCHITECT 2026-10-07 (addendum 6, 3): the Desk's own |div| >= staleGapPP flag, as the file wrote
                # it; a file without the field is unknown (None), never counted as false
                "stale_book_zone": d.get("stale_book_zone"),
                "conflicting_copies": bool(twins), "host_only": foreign}
    return sorted(by_key.values(), key=lambda c: (c["as_of"], c["sport"], str(c["home"])))


def claim_time(c: dict) -> tuple[datetime | None, str]:
    """The FROZEN claim time of a ledger position. The Cockpit's upsertCalls() re-log merges {...cur, ...fresh}:
    top-level claim_as_of / captured_at become the NEWEST file's, while stampTiming() keeps the first capture in
    claim_at (set once, isNew) and appends every capture to reprices[]. So claim_at first; a position logged
    before the timing rule has no claim_at, and its claim_as_of / captured_at is used, labelled."""
    t = parse_ts(c.get("claim_at"))
    if t is not None:
        return t, "claim_at (frozen first claim)"
    t = parse_ts(c.get("claim_as_of"))
    if t is not None:
        return t, "claim_as_of (no claim_at: the latest log's, unfrozen)"
    t = parse_ts(c.get("captured_at"))
    return t, ("captured_at (no claim_at: the latest log's, unfrozen)" if t is not None else "no claim time")


def claim_prices(c: dict, relogged: bool) -> dict:
    """The prices AT THE CLAIM (Codex on #340): upsertCalls() overwrites model_p / market_p / kalshi_p /
    divergence_pp with every re-log, while stampTiming() freezes claim_model_p / claim_market_p at the first claim.
    Never re-logged: the top-level fields ARE the claim's. Re-logged: book p = claim_model_p, Kalshi p =
    claim_market_p when no executable cost was used (else unknown), div = unknown; an unknown claim-time field is
    None and named in price_basis, never filled with the latest reprice."""
    if not relogged:
        return {"book_p": c.get("model_p"), "kalshi_p": c.get("kalshi_p", c.get("market_p")),
                "div_pp": c.get("divergence_pp"), "price_basis": "the claim's own log (never re-logged)"}
    # Codex on #340: for a venue claim, snapshotCalls() puts the executable cost in market_p (Kalshi's indicative
    # price rides in kalshi_p) and never sets kalshi_exec_cost, so stampTiming() freezes the cost in claim_market_p
    # with claim_exec_cost null. claim_market_p therefore cannot be told apart from a Kalshi price: claim-time Kalshi
    # p of a re-logged venue claim is UNKNOWN (never the exec cost, never the latest reprice)
    kal = None
    missing = [k for k, v in (("book p", c.get("claim_model_p")), ("Kalshi p", kal)) if v is None] + ["div"]
    return {"book_p": c.get("claim_model_p"), "kalshi_p": kal, "div_pp": None,
            "price_basis": "frozen claim fields; unknown at the claim: " + ", ".join(missing)}


def ledger_venue_calls(L: dict, since: datetime) -> list[dict]:
    """The Cockpit ledger's venue_edge claims (snapshotCalls logs only eligible VENUE rows) at claim time >= since.
    Claim time = claim_time() (claim_at, the frozen first claim; else claim_as_of / captured_at, labelled). One
    position is ONE call: its later re-logs (reprices[] after the claim) are reported on it, never counted as
    separate calls."""
    out = []
    for c in (L or {}).get("calls") or []:
        if not isinstance(c, dict) or c.get("engine") != "venue_edge":
            continue
        t, basis = claim_time(c)
        if t is None or t < since:
            continue
        reps = [x for x in (parse_ts(r.get("at")) for r in (c.get("reprices") or []) if isinstance(r, dict))
                if x is not None and x > t]            # Codex on #340: full precision (ms re-logs kept); only
        # AFTER the claim time is a later re-log (a legacy claim's fallback time is the latest log's; earlier
        # entries are listed apart, never as re-logs after the claim)
        before = sorted(x for x in (parse_ts(r.get("at")) for r in (c.get("reprices") or []) if isinstance(r, dict))
                        if x is not None and x < t)
        out.append({"origin": "ledger", "files": [], "in_ledger": True, "as_of": t, "claim_basis": basis,
                    "claim_source": c.get("claim_source"),
                    "reprices": sorted(reps), "reprices_before_claim": before, "foreign_ids": [],
                    "sport": str(c.get("sport") or "?").upper(), "match_id": None, "home": c.get("home"),
                    "away": c.get("away"), "kickoff": parse_ts(c.get("kickoff")), "side": c.get("pick"),
                    "units": c.get("units"), **claim_prices(c, bool(reps)), "file_fair": None, "file_books": None,
                    "file_captured_at": None,
                    # Codex on #340: the ledger keeps no fair_source; where a spread fallback can be the reference
                    # (NFL / NCAA), a ledger-only claim's source is UNKNOWN and is never measured on 1X2 captures
                    "fair_source": (LEDGER_UNKNOWN_SOURCE if str(c.get("sport") or "").upper() in SPREAD_SPORTS
                                    else None)})
    return out


def merge_calls(file_calls: list[dict], ledger_calls: list[dict]) -> list[dict]:
    """A ledger claim of a call already on file marks it in_ledger and carries the claim's reprices; a ledger claim
    with no file on disk is its own row. Match first on (sport, teams, kickoff, side, as_of — the claim's FROZEN
    time, to the second): an auto-claim's clock is the file's desk_meta.as_of. A MANUAL claim ("Log today's
    calls") is stamped at the button click, never a file's as_of, so it falls back to the position's identity
    (sport, teams, kickoff, side — the Cockpit's instKey): the file it was logged from is the latest file call of
    that position at or before the click. No such file call: its own row (never guessed onto a later file)."""
    def ident(c):
        return (c["sport"], c["home"], c["away"], _sec(c["kickoff"]), c["side"])

    def key(c):
        return ident(c) + (_sec(c["as_of"]),)
    def same(a, b, k=None):
        # Codex on #340: the Cockpit serializes divergence_pp with toFixed(2); compare div at 2dp, probabilities
        # within 5e-4
        if a is None or b is None:
            return False
        if k == "div_pp":                  # the Cockpit's toFixed(2) (ties away from zero), never ties-to-even
            from src.walters.desk_policy import js_fixed
            return js_fixed(float(a), 2) == js_fixed(float(b), 2)
        return abs(float(a) - float(b)) < 5e-4

    def pick(cands, claim):
        """One file call among same-key candidates (conflicting copies, Codex on #340): the one whose book p,
        Kalshi p and div the claim carries; no unique match -> None (ambiguous, never chosen silently)."""
        priced = any(claim.get(k) is not None for k in ("book_p", "kalshi_p", "div_pp"))
        if len(cands) == 1 and not priced:
            return cands[0]                    # a claim with no frozen price has nothing to contradict
        # Codex on #340: one candidate is checked too; a claim whose prices contradict the file attaches to none
        fit = [f for f in cands if all(same(f.get(k), claim.get(k), k) for k in ("book_p", "kalshi_p", "div_pp")
                                       if claim.get(k) is not None)
               and any(claim.get(k) is not None for k in ("book_p", "kalshi_p", "div_pp"))]
        return fit[0] if len(fit) == 1 else None
    idx: dict = {}
    by_pos: dict = {}
    for c in file_calls:
        idx.setdefault(key(c), []).append(c)
        by_pos.setdefault(ident(c), []).append(c)
    extra = []
    for c in ledger_calls:
        cands = idx.get(key(c)) or []
        basis = c.get("claim_basis")
        if not cands and c.get("claim_source") != "auto":
            # Codex on #340: only a MANUAL claim falls back by position; an auto-claim's clock IS its file's as_of,
            # so a missing exact file means its source export is unavailable (it stays its own row)
            prior = [f for f in by_pos.get(ident(c), []) if f["as_of"] <= c["as_of"] and not f["in_ledger"]]
            if prior:
                last = max(f["as_of"] for f in prior)
                cands = [f for f in prior if f["as_of"] == last]
                basis = f"{basis}; matched by position identity (manual claim at {_z(c['as_of'])})"
        hit = pick(cands, c) if cands else None
        if cands and hit is None:
            for f in cands:
                f["ledger_ambiguous"] = (
                    f"a ledger claim matches {len(cands)} conflicting file calls and its book p / Kalshi p / div name "
                    "none uniquely: attached to none" if len(cands) > 1 else
                    "a ledger claim of this call carries book p / Kalshi p / div that contradict this file's: "
                    "attached to none")
            continue
        if hit is not None:
            hit["in_ledger"] = True
            hit["reprices"] = c.get("reprices") or []
            hit["reprices_before_claim"] = c.get("reprices_before_claim") or []
            hit["claim_basis"] = basis
        else:
            extra.append(c)
    return sorted(file_calls + extra, key=lambda c: (c["as_of"], c["sport"], str(c["home"])))


# ---------------------------------------------------------- the captures --

def sessions_from_snapshots(snaps, outcomes: tuple[str, ...]) -> list[dict]:
    """BOOK consensus sessions, oldest first: [{source, t, fair (normalised), fair4, books}]. A session missing an
    outcome is not a price (the #207 contract) and is skipped."""
    by: dict = {}
    for x in snaps:
        if (getattr(x, "source", None) == "kalshi" or x.market != "1X2" or x.captured_at is None
                or x.devig_prob is None):
            continue
        by.setdefault((x.source, x.captured_at), {})[x.selection] = x
    out = []
    for (src, t), legs in by.items():
        if not all(k in legs for k in outcomes):
            continue
        tot = sum(legs[k].devig_prob for k in outcomes)
        if tot <= 0:
            continue
        fair = {k: legs[k].devig_prob / tot for k in outcomes}
        out.append({"source": src, "t": t, "fair": fair, "fair4": _r4(fair),
                    "books": max((legs[k].n_books or 0) for k in outcomes)})
    return sorted(out, key=lambda x: (x["t"], str(x["source"])))


def unchanged_run(sessions: list[dict], ref: dict) -> tuple[dict, int, bool]:
    """Walking back from `ref` through the SAME source's sessions while fair4 is identical: (earliest identical
    session, sessions in the run, censored = the run reaches the first capture on file)."""
    same = [x for x in sessions if x["source"] == ref["source"] and x["t"] <= ref["t"]]
    first, n = ref, 0
    for x in reversed(same):
        if x["fair4"] != ref["fair4"]:
            return first, n, False
        first, n = x, n + 1
    return first, n, True


def anchor_for(sessions: list[dict], call: dict) -> tuple[dict | None, str]:
    """The capture behind a call. File call with a captured_at: the session AT that stamp (preferring the one whose
    fair4 equals the file's), else the last one before it. Ledger-only call: the last session at or before the
    claim time. Captures at/after kickoff never count."""
    pre = [x for x in sessions if call["kickoff"] is None or x["t"] < call["kickoff"]]
    cap = call.get("file_captured_at")
    if cap is not None and call.get("as_of") is not None and _sec(cap) > _sec(call["as_of"]):
        # Codex on #340: a capture after the decision was not the consensus at the call (the venue engine itself
        # refuses one): unmeasured, never a verdict
        return None, "the file's captured_at is after the call time (not available at the call)"
    if cap is not None:
        exact = [x for x in pre if x["t"] == cap]
        if exact:
            same = [x for x in exact if call.get("file_fair") and x["fair4"] == call["file_fair"]]
            return (same or exact)[-1], "the capture at the file's captured_at"
        before = [x for x in pre if x["t"] <= cap]
        return (before[-1], "last capture before the file's captured_at (no capture at that stamp)") if before \
            else (None, "no book capture at or before the file's captured_at")
    # a file as_of is serialized to the second (Codex on #340); a ledger claim_at keeps milliseconds: full precision
    sec = (lambda t: t) if call.get("origin") == "ledger" else _sec
    before = [x for x in pre if sec(x["t"]) <= call["as_of"]]
    return (before[-1], "last capture at or before the call time (the call carries no captured_at)") if before \
        else (None, "no book capture at or before the call time")


def _side_key(call: dict, fair: dict) -> str | None:
    """The outcome key (HOME / AWAY / DRAW) of a call's side: the key itself, or the team named home / away."""
    side = call.get("side")
    if side in fair:
        return side
    if side is not None and side == call.get("home") and "HOME" in fair:
        return "HOME"
    if side is not None and side == call.get("away") and "AWAY" in fair:
        return "AWAY"
    return None


def receipt_row(call: dict, sessions: list[dict], anchor_verified_by: str | None = None) -> dict:
    a, basis = anchor_for(sessions, call)
    row = {**call, "anchor": a, "anchor_basis": basis, "later": [], "moved": None, "verdict": None,
           "file_matches_anchor": None, "unchanged_since": None, "run_n": 0, "run_censored": None}
    if a is None:
        row["verdict"] = "NO ANCHOR"
        return row
    if call.get("file_fair"):
        row["file_matches_anchor"] = same_fair(call["file_fair"], a["fair4"])        # LITERAL snapshot equality
        if anchor_verified_by and not row["file_matches_anchor"]:
            row["anchor_verified_by"] = anchor_verified_by     # the same session, re-derived (Codex on #340)
    first, n, cens = unchanged_run(sessions, a)
    row.update(unchanged_since=first["t"], run_n=n, run_censored=cens)
    if not call.get("files") and call.get("origin") == "ledger":
        # Codex on #340: a ledger-only claim carries no file fair; its frozen book p must be the anchor's own side
        # probability, else the anchor is a substitute session and no movement verdict is given
        key = _side_key(call, a["fair4"])
        bp = call.get("book_p")
        if bp is None or key is None:
            row["verdict"] = "LEDGER UNVERIFIED: NOT MEASURED"
            row["anchor_basis"] += " · the claim's book p / side cannot be checked against it"
            return row
        if abs(float(bp) - a["fair4"][key]) >= 5e-4:
            row["verdict"] = "ANCHOR MISMATCH: NOT MEASURED"
            row["anchor_basis"] += f" · claim book p {float(bp):.4f} != anchor {key} {a['fair4'][key]:.4f}"
            return row
    if row["file_matches_anchor"] is False and not row.get("anchor_verified_by"):
        # Codex on #340: an anchor whose fair is not the call's own fair is a substitute session; movement measured
        # from it says nothing about the call's quote, so no verdict
        row["verdict"] = "ANCHOR MISMATCH: NOT MEASURED"
        return row
    later = [x for x in sessions if x["source"] == a["source"] and x["t"] > a["t"]
             and (call["kickoff"] is None or x["t"] < call["kickoff"])]
    row["later"] = [{**x, "moved": x["fair4"] != a["fair4"]} for x in later]
    if not later:
        row["verdict"] = "NO LATER CAPTURE"
    else:
        row["moved"] = any(x["moved"] for x in row["later"])
        row["verdict"] = "MOVED" if row["moved"] else "NEVER MOVED"
    return row


def _outcomes(match) -> tuple[str, ...]:
    from src.walters.close import outcomes_for
    return outcomes_for(match.sport)


def schema_sport(s, code):
    """The schema Sport of a call's sport / competition code (NFL, NHL, MLB directly; PL, NCAA, … through the
    Competition row). None when unknown: the lookup is then not sport-filtered, and the receipt says so."""
    from src.db.schema import Competition, Sport
    if not code or code == "?":
        return None
    try:
        return Sport(str(code).lower())
    except ValueError:
        pass
    c = s.query(Competition).filter(Competition.code == str(code)).first()
    return c.sport if c is not None else None


def _identity_ok(m, call: dict, sport=None) -> bool:
    """The DB row IS the exported game: same sport (when known), exact home/away names and kickoff within ±12h."""
    if sport is not None and m.sport != sport:
        return False
    return bool(m.home_team is not None and m.away_team is not None and m.utc_date is not None
                and call.get("kickoff") is not None and m.home_team.name == call.get("home")
                and m.away_team.name == call.get("away") and abs(m.utc_date - call["kickoff"]) <= WINDOW)


def resolve_match(s, call: dict):
    """The DB match of a call or export row, by STABLE identity (match_id is machine-local):
      - a LOCAL match_id is used only when the DB row's teams + kickoff equal the exported home/away/utc_date;
      - otherwise (mirrored file, id missing from the DB, or an id naming another game) by exact team names with
        kickoff within ±12h.
    Returns (match, how): how = "match_id (verified …)" / "identity (…)"; ambiguous or none -> (None, reason):
    never guessed."""
    from sqlalchemy import select
    from src.db.schema import Match, Team
    why = ("mirrored file: foreign match_id never used" if call.get("foreign_ids") and call.get("match_id") is None
           else "no match_id")
    sport = schema_sport(s, call.get("sport"))           # Codex on #340: Team and Match are sport-scoped
    if call.get("match_id") is not None:
        m = s.get(Match, call["match_id"])
        if m is not None and _identity_ok(m, call, sport):
            return m, "match_id (verified: teams + kickoff)"
        why = (f"match_id {call['match_id']} not in the DB" if m is None else
               f"match_id {call['match_id']} is a different game in this DB")
    if not (call.get("home") and call.get("away") and call.get("kickoff")):
        return None, f"{why}; no teams/kickoff to resolve by identity — not guessed"
    tq = lambda name: select(Team).where(Team.name == name, *([Team.sport == sport] if sport is not None else []))
    hid = [t.id for t in s.execute(tq(call["home"])).scalars()]
    aid = [t.id for t in s.execute(tq(call["away"])).scalars()]
    ms = list(s.execute(select(Match).where(
        Match.home_team_id.in_(hid or [-1]), Match.away_team_id.in_(aid or [-1]),
        *([Match.sport == sport] if sport is not None else []),
        Match.utc_date >= call["kickoff"] - WINDOW,
        Match.utc_date <= call["kickoff"] + WINDOW)).scalars())
    scope = f"sport {sport.value}" if sport is not None else f"sport unknown for {call.get('sport')!r}: not filtered"
    if len(ms) != 1:
        return None, (f"{why}; {len(ms)} DB matches for {call['away']} @ {call['home']} ±12h ({scope}) — "
                      "not guessed")
    return ms[0], f"identity (team names + kickoff ±12h, {scope}; {why})"


def match_sessions(s, match) -> list[dict]:
    from sqlalchemy import select
    from src.db.schema import OddsSnapshot
    snaps = list(s.execute(select(OddsSnapshot).where(OddsSnapshot.match_id == match.id,
                                                      OddsSnapshot.market == "1X2")).scalars())
    return sessions_from_snapshots(snaps, _outcomes(match))


def venue_receipt(s, calls: list[dict]) -> dict:
    rows = []
    for c in calls:
        m, how = resolve_match(s, c)
        if m is None:
            rows.append({**c, "export_match_id": c.get("match_id"), "match_id": None, "resolved_by": None,
                         "anchor": None, "anchor_basis": how, "later": [], "moved": None,
                         "verdict": "NO DB MATCH", "file_matches_anchor": None, "unchanged_since": None,
                         "run_n": 0, "run_censored": None})
            continue
        c = {**c, "export_match_id": c.get("match_id"), "match_id": m.id, "resolved_by": how,
             "kickoff": c["kickoff"] or m.utc_date}
        if c.get("fair_source") is None and str(c.get("sport") or "").upper() in SPREAD_SPORTS:
            # Codex on #340: an NFL / NCAA file call that lost market.fair_source may be spread-derived; its source
            # is UNKNOWN (as for a ledger-only claim), never assumed to be 1X2
            c = {**c, "fair_source": "unknown (the file carries no fair_source)"}
        if c.get("fair_source") not in (None, "1X2"):
            # Codex on #340: a call whose reference is not the 1X2 consensus (an NCAA spread_derived fair) has no
            # 1X2 session behind it; this DB's 1X2 sessions never give it an anchor or a movement verdict
            rows.append({**c, "anchor": None, "anchor_basis": f"reference is {c['fair_source']}, not known to be the "
                         "1X2 consensus: no 1X2 capture history behind it", "later": [], "moved": None,
                         "verdict": "NOT 1X2: NOT MEASURED", "file_matches_anchor": None, "unchanged_since": None,
                         "run_n": 0, "run_censored": None})
            continue
        if c.get("origin") == "file" and not c.get("file_fair"):
            # Codex on #340: a file VENUE call with no (complete) fair cannot verify its anchor; never measured
            rows.append({**c, "anchor": None, "anchor_basis": "the file carries no fair_prob: the anchor could never "
                         "be verified", "later": [], "moved": None, "verdict": "NO FILE FAIR: NOT MEASURED",
                         "file_matches_anchor": None, "unchanged_since": None, "run_n": 0, "run_censored": None})
            continue
        if c.get("origin") == "file" and c.get("file_captured_at") is None:
            # Codex on #340: a VENUE export row with no parseable market.captured_at has no recorded reference
            # capture; never substitute the last capture before as_of
            rows.append({**c, "anchor": None, "anchor_basis": "the file's market.captured_at is missing or "
                         "unparseable: no recorded reference capture", "later": [], "moved": None,
                         "verdict": "NO CAPTURE TIME: NOT MEASURED", "file_matches_anchor": None,
                         "unchanged_since": None, "run_n": 0, "run_censored": None})
            continue
        if c.get("host_only"):
            # Codex on #340: a call only the HOST's files hold was decided on the host's captures; this DB's
            # sessions are the laptop's, fetched at other times, so they never give it a movement verdict
            rows.append({**c, "anchor": None, "anchor_basis": "host-only call: the host's capture history is not "
                         "in this DB", "later": [], "moved": None, "verdict": "HOST: NOT MEASURED",
                         "file_matches_anchor": None, "unchanged_since": None, "run_n": 0, "run_censored": None})
            continue
        sessions = match_sessions(s, m)
        r = receipt_row(c, sessions)
        if r["verdict"] == "ANCHOR MISMATCH: NOT MEASURED" and r.get("anchor"):
            # Codex on #340: the NCAA / NFL snapshot formula differs from the export's (close_1x2); re-derive the
            # SAME session from its odds rows with the export's formula before calling the anchor a mismatch
            ok, by = session_matches_by_odds(s, m, r["anchor"], c.get("file_fair"))
            if ok:
                r = receipt_row(c, sessions, anchor_verified_by=by)
        rows.append(r)
    tot = {"calls": len(rows)}
    for v in ("NEVER MOVED", "MOVED", "NO LATER CAPTURE", "NO ANCHOR", "NO DB MATCH", "HOST: NOT MEASURED",
              "NOT 1X2: NOT MEASURED", "ANCHOR MISMATCH: NOT MEASURED", "NO CAPTURE TIME: NOT MEASURED",
              "NO FILE FAIR: NOT MEASURED", "LEDGER UNVERIFIED: NOT MEASURED"):
        tot[v] = sum(1 for r in rows if r["verdict"] == v)
    tested = tot["NEVER MOVED"] + tot["MOVED"]
    tot["tested"] = tested
    tot["never_moved_share_of_tested"] = (tot["NEVER MOVED"] / tested) if tested else None
    tot["never_moved_share_of_calls"] = (tot["NEVER MOVED"] / len(rows)) if rows else None
    # ARCHITECT 2026-10-07 (addendum 6, 3): "count how many past VENUE calls carried stale_book_zone true"
    clean = [r for r in rows if not r.get("stale_book_zone_conflict")]
    tot["stale_book_zone_true"] = sum(1 for r in clean if r.get("stale_book_zone") is True)
    tot["stale_book_zone_false"] = sum(1 for r in clean if r.get("stale_book_zone") is False)
    tot["stale_book_zone_conflict"] = len(rows) - len(clean)
    tot["stale_book_zone_unknown"] = len(clean) - tot["stale_book_zone_true"] - tot["stale_book_zone_false"]
    tot["repriced_positions"] = sum(1 for r in rows if r.get("reprices"))
    tot["reprices"] = sum(len(r.get("reprices") or []) for r in rows)
    return {"rows": rows, "totals": tot}


# ------------------------------------------------------------ formatting --

def _z(t) -> str:
    return "—" if t is None else t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _f4(fair) -> str:
    if not fair:
        return "—"
    order = [k for k in ("HOME", "DRAW", "AWAY") if k in fair]
    return " / ".join(f"{k} {fair[k]:.4f}" for k in order)


def _share(x) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def format_venue_receipt(res: dict, since: datetime, sources: list[str]) -> list[str]:
    t = res["totals"]
    out = [f"VENUE CALLS RECEIPT (ARCHITECT 2026-10-07, venue-edge quote age) · VENUE calls on file since "
           f"{_z(since)} · READ-ONLY",
           "on file: " + ("; ".join(sources) or "nothing"),
           f"consensus = book capture session (odds_snapshots, 1X2, every outcome, source != kalshi), compared at "
           f"{DP} decimals; captures are OUR fetch times, not quote times"]
    for r in res["rows"]:
        out.append("")
        out.append(f"{r['sport']} · {r['away']} @ {r['home']} · KO {_z(r['kickoff'])} · VENUE {r['units']}u on "
                   f"{r['side']} · call as_of {_z(r['as_of'])} · "
                   f"div {'—' if r['div_pp'] is None else format(r['div_pp'], '+.2f')}pp · book "
                   f"{'—' if r['book_p'] is None else format(r['book_p'], '.4f')} vs Kalshi "
                   f"{'—' if r['kalshi_p'] is None else format(r['kalshi_p'], '.4f')}")
        out.append(f"  source: {'; '.join(r['files']) or 'ledger only'}" + (" · in ledger" if r["in_ledger"]
                                                                             and r["files"] else ""))
        sbz = r.get("stale_book_zone")
        out.append("  stale_book_zone (the Desk's |div| >= 8pp flag, as written): "
                   + (f"CONFLICTING across copies ({', '.join(r['stale_book_zone_conflict'])})"
                      if r.get("stale_book_zone_conflict") else
                      "TRUE" if sbz is True else "false" if sbz is False else "unknown (not on file)"))
        if r.get("ledger_ambiguous"):
            out.append(f"  LEDGER AMBIGUOUS: {r['ledger_ambiguous']}")
        if r.get("conflicting_copies"):
            out.append("  CONFLICT: another file holds this call (same teams, kickoff, side, as_of) with different "
                       "market numbers; each is listed as its own call, never merged as a copy")
        out.append(f"  DB match: {r['match_id'] if r['match_id'] is not None else '—'} via "
                   f"{r.get('resolved_by') or 'unresolved'}"
                   + (f" · foreign (host) id(s) {r['foreign_ids']} not used" if r.get("foreign_ids") else ""))
        if r.get("claim_basis"):
            out.append(f"  ledger claim time: {r['claim_basis']}")
            if r.get("price_basis"):
                out.append(f"  ledger claim prices: {r['price_basis']}")
        if r.get("reprices_before_claim"):
            out.append(f"  {len(r['reprices_before_claim'])} log(s) before the claim time (not re-logs after it): "
                       + ", ".join(_z(x) for x in r["reprices_before_claim"]))
        if r.get("reprices"):
            out.append(f"  re-logged {len(r['reprices'])} time(s) after the claim (one position, not extra calls): "
                       + ", ".join(_z(x) for x in r["reprices"]))       # every re-log (Codex on #340)
        if r.get("file_fair"):
            out.append(f"  AT THE CALL (file): {_f4(r['file_fair'])} · books {r['file_books']} · captured_at "
                       f"{_z(r['file_captured_at'])} · fair_source {r['fair_source']}")
        a = r["anchor"]
        if a is None:
            out.append(f"  ANCHOR: none — {r['anchor_basis']} · VERDICT {r['verdict']}")
            continue
        out.append(f"  ANCHOR ({r['anchor_basis']}): {_z(a['t'])} · {a['source']} · {_f4(a['fair4'])} · books "
                   f"{a['books']}" + ("" if r["file_matches_anchor"] is None else
                                      f" · file == anchor snapshot at {DP}dp: "
                                      f"{'yes' if r['file_matches_anchor'] else 'NO'}")
                   + (f" · verified instead by {r['anchor_verified_by']}" if r.get("anchor_verified_by") else ""))
        out.append(f"  identical at {DP}dp since {_z(r['unchanged_since'])} ({r['run_n']} capture(s)"
                   + (", reaches the first capture on file" if r["run_censored"] else "") + ")")
        for x in r["later"]:
            out.append(f"    later {_z(x['t'])} · {_f4(x['fair4'])} · books {x['books']} · "
                       f"{'MOVED' if x['moved'] else 'unchanged'}")
        out.append(f"  VERDICT: {r['verdict']} ({len(r['later'])} later pre-kickoff capture(s))")
    out.append("")
    out.append(f"TOTALS · calls {t['calls']} · tested (>= 1 later pre-kickoff capture) {t['tested']} · NEVER MOVED "
               f"{t['NEVER MOVED']} ({_share(t['never_moved_share_of_tested'])} of tested, "
               f"{_share(t['never_moved_share_of_calls'])} of calls) · MOVED {t['MOVED']} · no later capture "
               f"{t['NO LATER CAPTURE']} · no anchor {t['NO ANCHOR']} · no DB match {t['NO DB MATCH']} · host-only, "
               f"not measured {t.get('HOST: NOT MEASURED', 0)} · non-1X2 reference, not measured "
               f"{t.get('NOT 1X2: NOT MEASURED', 0)} · anchor != the call's fair, not measured "
               f"{t.get('ANCHOR MISMATCH: NOT MEASURED', 0)} · no capture time on file, not measured "
               f"{t.get('NO CAPTURE TIME: NOT MEASURED', 0)} · no fair on file, not measured "
               f"{t.get('NO FILE FAIR: NOT MEASURED', 0)} · ledger-only claim unverifiable against its anchor, not "
               f"measured {t.get('LEDGER UNVERIFIED: NOT MEASURED', 0)}")
    out.append(f"  stale_book_zone on the call: TRUE {t.get('stale_book_zone_true', 0)} · false "
               f"{t.get('stale_book_zone_false', 0)} · unknown (ledger-only or not on file) "
               f"{t.get('stale_book_zone_unknown', 0)} · conflicting across copies "
               f"{t.get('stale_book_zone_conflict', 0)} — the Desk's own flag, as written; it never held a call")
    out.append(f"  (re-logged ledger positions {t['repriced_positions']}, {t['reprices']} re-log(s): counted once "
               f"each, at the frozen claim)")
    return out


# --------------------------------------------- (4) model-sport reference age --

def pct(xs: list[float], q: float):
    if not xs:
        return None
    s = sorted(xs)
    # nearest rank, ties half-up (Codex on #340: Python's round() is ties-to-even, so .5 indices alternated)
    return s[min(len(s) - 1, int(math.floor(q * (len(s) - 1) + 0.5)))]


def _row_sport(doc: dict, row: dict) -> str:
    # Codex on #340: the same precedence doc_ident_ok accepts (a document's top-level competition counts)
    return str(row.get("competition") or doc.get("competition_code") or doc.get("competition") or doc.get("sport")
               or "?").upper()


def _row_fair(row: dict) -> dict | None:
    mk = row.get("market") or {}
    if isinstance(mk.get("selections"), dict) and mk["selections"]:
        return _r4({k: (v or {}).get("fair_prob") for k, v in mk["selections"].items()
                    if (v or {}).get("fair_prob") is not None})
    if isinstance(mk.get("fair_prob"), dict) and mk.get("fair_source", "1X2") == "1X2":
        return _r4(mk["fair_prob"])
    return None


def model_reference_rows(docs, since: datetime, mirrored=()) -> list[dict]:
    """Every --desk prediction-export row of MLB/NFL/PL whose desk decided against a BOOK reference
    (desk.reference == "books"), excluding started rows (no decision): pass_kind "started", or as_of at or after
    the kickoff (files older than the started-game rule carry no marker). One per (sport, home, away, kickoff,
    as_of) — stable identity; a mirrored file's match_id is foreign and kept only for the record."""
    mirrored = set(mirrored or ())
    seen, out = set(), []
    for path, doc in docs:
        if not isinstance(doc.get("predictions"), list):
            continue
        as_of = parse_ts(doc["desk_meta"].get("as_of"))
        if as_of is None or as_of < since:
            continue
        for r in doc["predictions"]:
            d = (r or {}).get("desk") or {}
            sport = _row_sport(doc, r)
            if (sport not in MODEL_SPORTS or d.get("engine") != "model_edge" or d.get("reference") != "books"
                    or d.get("pass_kind") == "started"):
                continue
            kick = parse_ts(r.get("utc_date"))
            if kick is not None and as_of >= kick:
                # Codex on #340: a file older than the started-game rule (2026-10-06) carries no pass_kind; a row
                # decided at or after kickoff is no decision, by its timestamps, whatever the marker says
                continue
            ident = (sport, r.get("home_team"), r.get("away_team"), kick, as_of)
            fair4 = _row_fair(r)
            mk = r.get("market") or {}
            if sport in SPREAD_SPORTS and mk.get("fair_source") is None and not (
                    isinstance(mk.get("selections"), dict) and mk["selections"]):
                # Codex on #340: only the fair_prob shape can be spread-derived without a label (the fixtures /
                # fallback block); a predictions export's market.selections is always export._summarize_market's
                # 1X2 close (close_1x2), so its fair stands
                fair4 = None
            raw = mk.get("fair_prob") if isinstance(mk.get("fair_prob"), dict) else {}
            # Codex on #340: the reference source and its RAW fair are part of copy identity (a spread_derived fair
            # has no 1X2 fair4, so two different spread references must not look identical)
            # the raw fair only where no 1X2 fair4 exists (a spread reference); 1X2 copies compare at 4dp (Codex)
            k = ident + (tuple(sorted((fair4 or {}).items())), mk.get("fair_source"),
                         () if fair4 else tuple(sorted((kk, vv) for kk, vv in raw.items())))
            foreign = path in mirrored
            if k in seen:                                  # a true copy (same identity AND same book fair)
                if not foreign:                            # Codex on #340: any LOCAL copy makes the row local,
                    for x in out:                          # whatever order the walk met the copies in
                        if x.get("_key") == k and x["mirrored"]:
                            x.update(mirrored=False, file=path, match_id=r.get("match_id"),
                                     foreign_ids=x["foreign_ids"])
                continue
            # Codex on #340: same identity, different book fair = two machines' references, both kept and flagged
            twins = [x for x in out if (x["sport"], x["home"], x["away"], x["kickoff"], x["as_of"]) == ident]
            for x in twins:
                x["conflicting_copies"] = True
            seen.add(k)
            out.append({"sport": sport, "match_id": None if foreign else r.get("match_id"),
                        "foreign_ids": [r.get("match_id")] if foreign else [], "home": r.get("home_team"),
                        "away": r.get("away_team"), "as_of": as_of, "file": path,
                        "kickoff": kick, "file_fair": fair4, "call": d.get("call"), "mirrored": foreign, "_key": k,
                        "conflicting_copies": bool(twins)})
    return out


def age_row(row: dict, sessions: list[dict]) -> dict:
    # Codex on #340: desk_meta.as_of is serialized to the second while captured_at keeps microseconds, so a capture
    # in the export's own second is compared at the second (and its age floors at 0)
    pre = [x for x in sessions if _sec(x["t"]) <= row["as_of"] and (row["kickoff"] is None or x["t"] < row["kickoff"])]
    if not pre:
        return {**row, "ref": None}
    ref = pre[-1]
    first, n, cens = unchanged_run(sessions, ref)
    return {**row, "ref": ref, "capture_age_h": max(0.0, (row["as_of"] - ref["t"]).total_seconds()) / 3600,
            "unchanged_age_h": max(0.0, (row["as_of"] - first["t"]).total_seconds()) / 3600, "run_n": n,
            "censored": cens,
            "file_matches": (None if not row["file_fair"] else
                             same_fair(row["file_fair"], ref["fair4"]))}


def exclusion(x: dict) -> str | None:
    """Why a row stays OUT of the age statistics (None = it enters). Only a row whose reference session is
    VERIFIED (the file's fair equals the selected capture at 4dp) is measured; an unverified session may not be
    the one behind the Desk's reference (multi-source history, an NFL spread_derived reference, …)."""
    if x.get("mirrored"):
        # Codex on #340: a host export was decided on the HOST's captures; this DB's odds_snapshots are the
        # laptop's, fetched at other times, so a 4dp match proves nothing about the host's capture time
        return "mirrored host export: the host's capture history is not in this DB (listed, never measured)"
    if x.get("ref") is None:
        return x.get("why") or "no book capture at or before as_of"
    if x.get("file_matches") is None:
        return "session unverified: the file carries no 1X2 fair to compare"
    if x["file_matches"] is False and not x.get("rederived"):
        why = x.get("verified_by")
        return f"session unverified: file fair != the selected capture at {DP}dp" + (f" ({why})" if why else "")
    return None


def session_matches_by_odds(s, match, ref: dict, file_fair: dict | None) -> tuple[bool, str]:
    """The file's fair re-derived for the selected session from the stored odds rows of that capture (same source,
    same captured_at), with close_1x2's per-book de-vig (the formula the exports use). (True, basis) when it equals
    the file's fair at 4dp; else (False, why). No odds rows for the session (a board since replaced): False, said."""
    from sqlalchemy import select

    from src.db.schema import Odds
    from src.walters.close import close_1x2, priced
    if not file_fair:
        return False, "no file fair"
    rows = list(s.execute(select(Odds).where(Odds.match_id == match.id, Odds.market == "1X2",
                                             Odds.captured_at == ref["t"], Odds.source == ref["source"])).scalars())
    if not rows:
        return False, "snapshot mismatch; no stored odds rows for that session to re-derive"
    cl = close_1x2(rows, None, _outcomes(match))
    if not priced(cl):
        return False, "snapshot mismatch; the session's odds rows hold no complete book"
    fair4 = _r4(cl["fair"])
    if same_fair(file_fair, fair4):
        return True, "odds rows of the session, per-book de-vig (the export's formula)"
    return False, "mismatch on the snapshot AND on the session's odds rows (per-book de-vig)"


def age_report(s, docs, since: datetime, mirrored=()) -> dict:
    rows = []
    for r in model_reference_rows(docs, since, mirrored):
        m, how = resolve_match(s, r)
        if m is None:
            rows.append({**r, "export_match_id": r.get("match_id"), "match_id": None, "resolved_by": None,
                         "ref": None, "why": f"no DB match: {how}"})
            continue
        r = {**r, "export_match_id": r.get("match_id"), "match_id": m.id, "resolved_by": how,
             "kickoff": r["kickoff"] or m.utc_date}
        x = age_row(r, match_sessions(s, m))
        if x.get("ref") is not None and x["file_matches"] is False:
            # Codex on #340: the NFL snapshot is de-vigged by average-then-normalise (sync-odds-football), the file's
            # fair by per-book normalise-then-average (close_1x2): they differ whenever books' overrounds differ.
            # Re-derive the SAME session from its stored odds rows with the file's own formula before calling it
            # unverified.
            ok, why = session_matches_by_odds(s, m, x["ref"], x["file_fair"])
            # Codex on #340: file_matches stays LITERAL snapshot equality; the re-derivation is tracked apart
            x["rederived"] = ok
            x["verified_by"] = why
        rows.append(x)
    for x in rows:
        x["excluded"] = exclusion(x)
    by = {}
    for sp in MODEL_SPORTS:
        rs = [x for x in rows if x["sport"] == sp]
        ok = [x for x in rs if x.get("ref") is not None and not x.get("mirrored")]   # host rows: no local evidence
        ver = [x for x in rs if x["excluded"] is None]                 # only VERIFIED sessions are measured
        ca, ua = [x["capture_age_h"] for x in ver], [x["unchanged_age_h"] for x in ver]
        by[sp] = {"rows": len(rs), "with_capture": len(ok), "measured": len(ver),
                  "excluded": len(rs) - len(ver),
                  "file_matches": sum(1 for x in ok if x["file_matches"]),
                  "file_rederived": sum(1 for x in ok if x["file_matches"] is False and x.get("rederived")),
                  "file_mismatch": sum(1 for x in ok if x["file_matches"] is False and not x.get("rederived")),
                  "file_unverifiable": sum(1 for x in ok if x["file_matches"] is None),
                  "capture_age_h": {"median": pct(ca, 0.5), "p90": pct(ca, 0.9), "max": max(ca) if ca else None},
                  "unchanged_age_h": {"median": pct(ua, 0.5), "p90": pct(ua, 0.9), "max": max(ua) if ua else None},
                  "censored": sum(1 for x in ver if x["censored"]),
                  "unchanged_ge_3h": sum(1 for x in ua if x > 3)}
    return {"rows": rows, "by_sport": by}


def _h(x) -> str:
    return "—" if x is None else f"{x:.2f}h"


def format_age_report(rep: dict, since: datetime, sources: list[str]) -> list[str]:
    out = [f"MODEL-SPORT REFERENCE AGE (ARCHITECT 2026-10-07 build step 4: report, do not change) · --desk "
           f"prediction exports since {_z(since)} · READ-ONLY",
           f"LABEL: {PROXY_LABEL}",
           "on file: " + ("; ".join(sources) or "nothing"),
           "rows = desk.engine model_edge with reference 'books', started rows excluded, one per (match, as_of)",
           "capture age   = desk as_of − the last book capture session (odds_snapshots) at or before as_of",
           f"unchanged age = desk as_of − the earliest capture of the run of consecutive same-source captures "
           f"identical at {DP}dp ending at that session (censored = the run reaches the first capture on file)",
           f"measured = rows whose selected session is VERIFIED (file fair == capture at {DP}dp); every other row is "
           f"excluded from median/p90/max and listed with its reason",
           "match identity: a local match_id only after teams + kickoff verify; mirrored (host) files by team names "
           "+ kickoff ±12h (match_id is machine-local)"]
    for sp, b in rep["by_sport"].items():
        ca, ua = b["capture_age_h"], b["unchanged_age_h"]
        out.append(f"{sp}: rows {b['rows']} · with a capture {b['with_capture']} · measured (verified) "
                   f"{b['measured']} · excluded {b['excluded']} · file fair == capture at {DP}dp "
                   f"{b['file_matches']} · verified by odds-row re-derivation instead {b.get('file_rederived', 0)} "
                   f"(mismatch {b['file_mismatch']}, no file fair {b['file_unverifiable']}; host rows not counted)")
        out.append(f"  capture age   median {_h(ca['median'])} · p90 {_h(ca['p90'])} · max {_h(ca['max'])}")
        out.append(f"  unchanged age median {_h(ua['median'])} · p90 {_h(ua['p90'])} · max {_h(ua['max'])} · "
                   f"> 3h {b['unchanged_ge_3h']} · censored {b['censored']}")
    conf = [x for x in rep["rows"] if x.get("conflicting_copies")]
    if conf:
        out.append(f"CONFLICTING COPIES (same match + as_of, different book fair; each kept as its own row): {len(conf)}")
        for x in conf:
            out.append(f"  {x['sport']} · {x.get('away')} @ {x.get('home')} · as_of {_z(x['as_of'])} · {x['file']} · "
                       f"fair {x.get('file_fair')}")
    exc = [x for x in rep["rows"] if x.get("excluded")]
    if exc:
        out.append(f"EXCLUDED from the statistics: {len(exc)}")
        for x in exc:                          # every one, with its reason (Codex on #340: no truncation)
            out.append(f"  {x['sport']} · {x.get('away')} @ {x.get('home')} · KO {_z(x.get('kickoff'))} · as_of "
                       f"{_z(x['as_of'])} · {x['excluded']}")
    return out
