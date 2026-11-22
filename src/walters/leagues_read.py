"""THE LEAGUES WINDOWS' ONE READ, AS A COMMAND (ARCHITECT 2026-11-22 09:18 ET, addendum 447 items 1, 2 and 4 PR 1;
lane leagues, #322; the plan, #322 issuecomment-7066669252, approved with the rulings of items 2 and 3).

`python cli.py leagues-window-read --code <PD|SA|FL1|ELC|BL1> --db COPY --exports DIR --pages-digest HEX` in three
invocations, each its own:
  1. `--preflight`: counts only, the first date the read is allowed, then the WINDOW FINGERPRINT. Scores nothing,
     reserves nothing, writes nothing.
  2. `--architect-word "<word>" --window-fingerprint HEX [--no-fetch]`: THE ONE READ.
  3. `--record-verdict PASS|REJECT --ruling "<the architect's words, verbatim>"` (B1, RULED: "a separate invocation.
     The verdict is recorded by --record-verdict --ruling after I have read the read's console, refused unless the
     run is recorded and my word equals the computed one").

WHERE AND ON WHAT (B2, RULED): the laptop, on the host's pulled .backup copy (`--db`) and the host's pages (`--exports`),
brought "by my OPERATOR block only, straight from the host's export directory over the tailnet, into a folder outside
the checkout and outside data/" (B2(a)). The registry writes (the reservation, record_run and its ids file, the
verdict) land in this checkout and travel by the laptop/<eid>-run-record branch (#329).

EVERY REFUSAL BEFORE ANYTHING IS SCORED, in this order (ReadRefused; the CLI prints REFUSED, exit 2; nothing reserved,
nothing written):
  1. the arguments: a code not one of the five; no --db, --exports or --pages-digest; in the run, no word or no
     fingerprint (before any load, as the gates refuse);
  2. the registry entry: absent; a run recorded; a verdict recorded; the read's reservation present (spent);
  3. the copy: addendum 346's fence (mlb_pitchers_gate.check_db: an existing file outside every data/, never the app's
     configured database, never created; no -wal/-shm/-journal beside it; each table the read touches probed through
     mode=ro + immutable=1), its sha256 taken before the read;
  4. the pages: the folder missing or not a folder; the folder INSIDE THE CHECKOUT (B2(b), RULED: "The read REFUSES an
     --exports folder inside the checkout, and never writes into the folder"); a page that cannot be read; no page; the
     digest (leagues_window.pages_digest, B2(c)) not the one given;
  5. the entry's own checks (leagues_window.checked: the league field, declared_at, the frozen constants against the
     run record) and its ruled list (ruled_items, #803), inside read();
  6. the window: read() on the copy and the pages must report "ready" (60 members, nothing pending before the 60th);
     every membership refusal holds here too;
  7. THE DAY AFTER (B2(d), RULED: "the read REFUSES while the UTC date of its clock is not later than the UTC date of
     the 60th member's kickoff");
  8. the fingerprint: the given --window-fingerprint must equal this stream's (window_fingerprint: the member ids in
     order, their stored rows, the ruled list, the copy's sha256, the pages digest, the frozen constants).
Then the #329 cross-ref guard and the reservation docs/registry/<eid>.started.json (exclusive create, serialised first,
written and fsynced with its directory, removed if the write fails: nothing spent). From there THE READ IS SPENT: the
score (leagues_window.score on the same copy session, which re-derives the window in its own derivation and refuses if
a member, the state or the ruled list moved), then the pages digest again, the copy's sha256 again and its sidecars
again; any failure there raises SpentRefused (the reservation stands; released by the architect's ruling only), and
nothing is recorded. Then record (registry.record_run: the 60 member ids, sorted, in the ids file; the result below in
the run record), the result checked JSON-serialisable BEFORE record_run is called (record_run writes the ids file first
and saves the ledger in place).

THE RUN RECORD (`result`): n, both mean log-losses unrounded, the computed verdict (PASS only when the candidate's is
strictly below the close's; a tie REJECTS: leagues_window.verdict_of); the members in the window's order; THE OPENING
(`confirmation_opens_after`, 447 C1: the 60th member's kickoff and match id, written by the one read before any verdict
exists); every game the window's loop reached that took no slot, by id, with its kickoff and cause (B2(e)); the audit's
counts, lists and lines; the frozen constants; the ruled list; the copy's sha256; the pages digest with its count and
first and last file; the word; the fingerprint; the read clock and the first allowed date.

Changes no prediction output: no prediction, export, Desk call or model is written or read differently; the reader's
print (leagues_window.lines) is unchanged.
"""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from src.walters import leagues_window as lw

COMMAND = "leagues-window-read"
CODES = tuple(lw.DECLARATION_IDS)
# Every table the read touches (membership, score: matches, competitions, teams, odds_snapshots), probed on the copy
# through the same mode=ro + immutable=1 URI before anything else is read (intl_shadow.check_copy's pattern).
COPY_TABLES = ("competitions", "matches", "teams", "odds_snapshots")
VERDICT_WORDS = ("PASS", "REJECT")
FINGERPRINT_TAG = "leagues-window-read v1"
RESERVATION_DIR = None              # None = the registry's own directory (docs/registry); tests point it elsewhere


class ReadRefused(RuntimeError):
    """A refusal before the reservation: nothing reserved, nothing written."""


class SpentRefused(ReadRefused):
    """A failure after the reservation: the reservation stands and the one read is spent (released only by the
    architect's ruling); nothing recorded."""


def _reg():
    from src.walters import registry as reg
    return reg


def _iso(t: datetime | None) -> str | None:
    return None if t is None else t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _jsonable(x):
    """The run record's values as JSON text: a datetime as its UTC stamp, a date as its ISO day, a tuple or set as a
    list, a Counter or dict with its keys as text. record_run must never meet a value json cannot write."""
    if isinstance(x, datetime):
        return _iso(x)
    if isinstance(x, date):
        return x.isoformat()
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (set, frozenset)):
        return [_jsonable(v) for v in sorted(x)]
    return x


# ------------------------------------------------------------------------------------------- 1. arguments --

def check_args(code, db, exports, pages_digest) -> str:
    c = (code or "").strip().upper()
    if c not in CODES:
        raise ReadRefused(f"--code {code!r}: not one of the five leagues windows ({', '.join(CODES)}); nothing read")
    for flag, v in (("--db", db), ("--exports", exports), ("--pages-digest", pages_digest)):
        if v is None or not str(v).strip():
            raise ReadRefused(f"{flag} is required (addendum 447 item 2 B2): the host's pulled .backup copy, the "
                              "host's pages and the digest the host printed; nothing read")
    d = str(pages_digest).strip().lower()
    if len(d) != 64 or any(ch not in "0123456789abcdef" for ch in d):
        raise ReadRefused(f"--pages-digest {pages_digest!r}: not a sha256 in hex; nothing read")
    return c


# ---------------------------------------------------------------------------------------- 2. the entry --

def reservation_path(eid: str) -> str:
    return os.path.join(RESERVATION_DIR or os.path.dirname(_reg().LEDGER), f"{eid}.started.json")


def _started_at(p: str) -> str:
    try:
        with open(p) as f:
            return json.load(f).get("started_at", "?")
    except (OSError, ValueError):
        return "?"


def check_entry(code: str) -> dict:
    """The declared entry, refused when absent, run, ruled, or its reservation present (the read is spent)."""
    eid = lw.DECLARATION_IDS[code]
    try:
        e = lw.declaration(code)
    except lw.WindowRefused as err:
        raise ReadRefused(f"{eid}: {err}") from err
    if e is None:
        raise ReadRefused(f"{eid}: no declared entry in the registry; nothing to read")
    if e.get("run"):
        raise ReadRefused(f"{eid}: a run is recorded ({e['run'].get('run_at', '?')}): the one read is spent")
    if e.get("verdict"):
        raise ReadRefused(f"{eid}: a verdict is recorded: the one read is spent")
    p = reservation_path(eid)
    if os.path.lexists(p):
        raise ReadRefused(f"{eid}: the one read was started at {_started_at(p)} ({os.path.relpath(p)}): it is spent, "
                          "recorded or not; nothing reads it again without the architect's ruling")
    return e


# ----------------------------------------------------------------------------------------- 3. the copy --

def check_copy(db) -> Path:
    """Addendum 346's fence, unchanged in substance (intl_shadow.check_copy's): mlb_pitchers_gate.check_db, then no
    -wal/-shm/-journal beside the copy, then each COPY_TABLES table probed through mode=ro + immutable=1."""
    import sqlite3

    from src.walters import intl_shadow as us
    from src.walters import mlb_pitchers_gate as mp
    try:
        path = mp.check_db(db)
        try:
            sides = us.copy_sidecars(path)
        except OSError as err:
            raise mp.GateRefused(f"--db {db}: a sidecar beside it cannot be checked ({err!r})") from None
        for name in sides:
            raise mp.GateRefused(f"--db {db} has a {name[len(path.name):]} sidecar ({name}): not a fresh .backup "
                                 "copy; immutable=1 would ignore it and read a stale store; take a fresh .backup copy")
        con = mp.open_ro(path)
        try:
            for t in COPY_TABLES:
                try:
                    con.execute(f"SELECT 1 FROM {t} LIMIT 1")
                except sqlite3.Error as e:
                    raise mp.GateRefused(f"--db {db}: the copy cannot be read for table {t} ({e})")
        finally:
            con.close()
    except mp.GateRefused as err:
        raise ReadRefused(f"{err}; nothing read, nothing reserved") from None
    return path


def copy_state(path: Path) -> tuple[str, list[str]]:
    from src.walters import intl_shadow as us
    try:
        return us.copy_sha256(path), us.copy_sidecars(path)
    except OSError as err:
        raise ReadRefused(f"--db {path}: cannot be hashed ({err}); nothing read") from err


# ---------------------------------------------------------------------------------------- 4. the pages --

def _roots() -> list[Path]:
    """The checkout this code runs from, and, from a worktree, the main checkout (mlb_pitchers_gate's own lookup)."""
    out = [Path(_reg().ROOT).resolve()]
    try:
        from src.walters import mlb_pitchers_gate as mp
        d = mp._main_checkout_data()
        if d is not None and d.parent.resolve() not in out:
            out.append(d.parent.resolve())
    except Exception:  # noqa: BLE001 - no git, or no worktree: this checkout alone
        pass
    return out


def inside_checkout(folder) -> bool:
    """B2(b): the folder, by its absolute path and by its resolved path, is a checkout's root or under it (compared by
    device and inode, so a symlink or another spelling of the same folder is found). A folder that does not exist is
    not inside (the pages check refuses it as missing)."""
    roots = []
    for r in _roots():
        try:
            st = os.stat(r)
            roots.append((st.st_dev, st.st_ino))
        except OSError:
            continue
    for cand in {Path(os.path.abspath(folder)), Path(folder).resolve()}:
        for p in (cand, *cand.parents):
            try:
                st = os.stat(p)
            except FileNotFoundError:
                continue
            if (st.st_dev, st.st_ino) in roots:
                return True
    return False


def check_pages(exports, given: str) -> dict:
    """Refused: the folder inside the checkout (B2(b)); missing, empty or unreadable (pages_digest); a digest that is
    not the given one (the laptop proves it holds exactly the pages the host digested, B2(c))."""
    if inside_checkout(exports):
        raise ReadRefused(f"--exports {exports}: inside the checkout (addendum 447 item 2 B2(b): the read REFUSES an "
                          "--exports folder inside the checkout); pull the host's pages into a folder outside it and "
                          "outside data/; nothing read")
    try:
        d = lw.pages_digest(exports)
    except lw.WindowRefused as err:
        raise ReadRefused(str(err)) from err
    if d["digest"] != str(given).strip().lower():
        raise ReadRefused(f"--exports {exports}: the pages digest is {d['digest']} ({d['pages']} pages, first "
                          f"{d['first']}, last {d['last']}), not the host's {given}: the folder does not hold exactly "
                          "the host's pages; nothing read")
    return d


# ------------------------------------------------------------------------------------- 5-8. the window --

def first_allowed(w: dict) -> date | None:
    """B2(d): the first UTC date the read is allowed, the day after the 60th member's kickoff's UTC date; None until
    there are 60 members."""
    last = w.get(lw.LAST_MEMBER)
    return None if not last else last[1].date() + timedelta(days=1)


def window_fingerprint(code: str, w: dict, stored: dict, copy_sha: str, digest: str) -> str:
    """sha256 over the member ids in the window's order, their stored rows, the ruled list, the copy's sha256, the pages
    digest and the frozen constants (the plan's list, approved). JSON, sorted keys, no whitespace."""
    import hashlib
    body = {"tag": FINGERPRINT_TAG, "code": code, "id": w.get("id"), "members": list(w["members"]),
            "stored_rows": [stored.get(i) for i in w["members"]],
            "ruled": _jsonable(sorted(w.get("ruled_items_read", {}).items())),
            "copy_sha256": copy_sha, "pages_digest": digest, "constants": dict(w["constants"])}
    blob = json.dumps(_jsonable(body), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
                      default=str)
    return hashlib.sha256(blob.encode("ascii")).hexdigest()


@contextmanager
def _copy_session(path: Path):
    from src.walters import mlb_pitchers_gate as mp
    with mp.readonly_session(path) as s:
        yield s


def _window(code: str, s, exports, now: datetime) -> dict:
    from sqlalchemy.exc import SQLAlchemyError
    try:
        w = lw.read((code,), now=now, export_dir=str(exports), s=s)[code]
    except lw.WindowRefused as err:
        raise ReadRefused(f"{lw.DECLARATION_IDS[code]}: {err}") from err
    except SQLAlchemyError as err:                 # the copy could not be read as the window reads it: never a traceback
        raise ReadRefused(f"{lw.DECLARATION_IDS[code]}: the copy could not be read ({type(err).__name__}: {err}); "
                          "nothing reserved") from err
    if not w.get("declared"):
        raise ReadRefused(f"{lw.DECLARATION_IDS[code]}: not declared; nothing to read")
    if w.get("refused"):
        raise ReadRefused(f"{lw.DECLARATION_IDS[code]}: the window refuses: {w['refused']}")
    return w


def load(code, e: dict, path: Path, exports, pages_digest, now: datetime, s=None):
    """Steps 3 (the copy's hash) to 6, after check_entry and check_copy: the pages, the window. Returns (copy_sha,
    pages, window, stored rows). With `s` given (the run), the window is read through it; else a session is opened
    and closed here (the preflight)."""
    sha, sides = copy_state(path)
    if sides:
        raise ReadRefused(f"--db {path}: a sidecar appeared ({', '.join(sides)}); nothing read")
    pages = check_pages(exports, pages_digest)
    if s is None:
        with _copy_session(path) as s2:
            w = _window(code, s2, exports, now)
    else:
        w = _window(code, s, exports, now)
    try:
        stored = lw.stored_rows(code, w.get("declared_at_text"), str(exports))
    except lw.WindowRefused as err:
        raise ReadRefused(str(err)) from err
    if pages["pages"] != w.get("export_pages"):
        raise ReadRefused(f"--exports {exports}: the digest counted {pages['pages']} pages and the read "
                          f"{w.get('export_pages')}: the folder changed under the read; nothing read")
    return sha, pages, w, stored


def _label(code, path, sha, pages) -> list[str]:
    from src.walters import mlb_pitchers_gate as mp
    return [f"  {lw.DECLARATION_IDS[code]} · --db {path} · sha256 {sha} · a .backup copy, opened "
            f"{mp.COPY_URI_QUERY.lstrip('?')} (the app's database is not read)",
            f"  --exports: {pages['pages']} pages · first {pages['first']} · last {pages['last']} · digest "
            f"{pages['digest']} = the host's (addendum 447 item 2 B2(c))"]


def preflight_lines(code, db, exports, pages_digest, now: datetime | None = None) -> list[str]:
    """--preflight: counts only (leagues_window.lines), the first date the read is allowed, then the fingerprint when
    the window is ready. Scores nothing, reserves nothing, writes nothing."""
    from src.timeutil import utc_now_naive
    now = now or utc_now_naive()
    code = check_args(code, db, exports, pages_digest)
    e = check_entry(code)
    path = check_copy(db)
    sha, pages, w, stored = load(code, e, path, exports, pages_digest, now)
    L = [f"LEAGUES WINDOW READ · PREFLIGHT · {code} · clock {_iso(now)} (scores nothing, reserves nothing, writes "
         "nothing; addendum 447 item 2)"]
    L += _label(code, path, sha, pages)
    L += lw.lines({code: w}, now)
    fa = first_allowed(w)
    if w["state"] != "ready":
        L.append(f"  the 60th member: {'not yet' if fa is None else 'provisional (the window is ' + w['state'] + ')'}"
                 + ("" if fa is None else f" · the first date the read would be allowed {fa.isoformat()} (UTC)"))
        L.append(f"PREFLIGHT only: the window is {w['state']!r}, not ready: NO fingerprint; the read refuses.")
        return L
    L.append(f"  the 60th member kicks off {_iso(w[lw.LAST_MEMBER][1])}: the read is allowed from {fa.isoformat()} "
             "(UTC), the day after (addendum 447 item 2 B2(d))"
             + ("" if now.date() >= fa else f" · NOT TODAY ({now.date().isoformat()}): the read refuses until then"))
    L.append(f"WINDOW FINGERPRINT {window_fingerprint(code, w, stored, sha, pages['digest'])} (the read takes it as "
             "--window-fingerprint)")
    return L


# ------------------------------------------------------------------------------------- the reservation --

def reserve(eid: str, meta: dict, no_fetch: bool = False, echo=None) -> str:
    """The #329 cross-ref guard, then the exclusive create of docs/registry/<eid>.started.json (nfl_v2_gate.reserve's
    shape: serialised first; written, fsynced, closed, its directory fsynced; on a failure removed: nothing spent)."""
    from src.walters import nfl_v2_gate as ng
    reg = _reg()
    p = reservation_path(eid)
    if os.path.lexists(p):
        raise ReadRefused(f"{eid}: the one read was started at {_started_at(p)}: it is spent")
    try:
        receipt = reg.cross_ref_guard(eid, no_fetch=no_fetch)
    except reg.RegistryError as err:
        raise ReadRefused(f"{err}; nothing reserved") from err
    if echo:
        echo(receipt)
    from src.timeutil import utc_now_naive
    try:
        data = (json.dumps({"id": eid, "started_at": _iso(utc_now_naive()), "guard": receipt, **meta},
                           allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError) as err:
        raise ReadRefused(f"{eid}: the reservation could not be serialised ({err}); nothing written") from err
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except OSError as err:
        raise ReadRefused(f"{eid}: the reservation could not be created ({type(err).__name__}: {err}); nothing "
                          "written, nothing scored") from err
    try:
        ng._write_all(fd, data)
        os.close(fd)
        fd = None
        ng._fsync_dir(p)
    except BaseException as err:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            os.unlink(p)
            ng._fsync_dir(p)
        except OSError as uerr:
            raise ReadRefused(f"{eid}: the reservation could not be written ({err}) nor removed ({uerr}): INSPECT "
                              f"{os.path.relpath(p)}") from err
        if not isinstance(err, Exception):
            raise
        raise ReadRefused(f"{eid}: the reservation could not be written ({err}); removed; nothing scored") from err
    return p


# ----------------------------------------------------------------------------------------- THE ONE READ --

def run(code, db, exports, pages_digest, word, fingerprint, now: datetime | None = None, no_fetch: bool = False,
        echo=None) -> dict:
    """THE ONE READ (the module docstring's order). Returns the result record() records."""
    from src.timeutil import utc_now_naive
    code = check_args(code, db, exports, pages_digest)
    eid = lw.DECLARATION_IDS[code]
    if not word or not str(word).strip():
        raise ReadRefused("the read starts only on the architect's word: pass --architect-word verbatim; nothing read")
    if not fingerprint or not str(fingerprint).strip():
        raise ReadRefused(f"the word refers to one window (the preflight's): pass --window-fingerprint with the last "
                          f"line of {COMMAND} --preflight; nothing read")
    now = now or utc_now_naive()
    e = check_entry(code)
    path = check_copy(db)               # opened once, so the read and the score share one immutable session
    with _copy_session(path) as s:
        sha, pages, w, stored = load(code, e, path, exports, pages_digest, now, s=s)
        if w["state"] != "ready":
            raise ReadRefused(f"{eid}: the window is {w['state']!r}, not ready (60 members, nothing pending before the "
                              "60th): the read WAITS; nothing reserved")
        fa = first_allowed(w)
        if now.date() < fa:
            raise ReadRefused(f"{eid}: the 60th member kicks off {_iso(w[lw.LAST_MEMBER][1])}; the read is allowed "
                              f"from {fa.isoformat()} (UTC), the day after (addendum 447 item 2 B2(d)), and the clock "
                              f"reads {now.date().isoformat()}; nothing reserved")
        fp = window_fingerprint(code, w, stored, sha, pages["digest"])
        if str(fingerprint).strip().lower() != fp:
            raise ReadRefused(f"the window fingerprint given ({fingerprint!r}) is not this window's ({fp}): run "
                              f"{COMMAND} --preflight again and take the word on it; nothing reserved")
        meta = {"architect_word": word, "window_fingerprint": fp, "copy_sha256": sha, "pages_digest": pages["digest"],
                "pages": pages["pages"], "code_sha": _code_sha()}
        held = reserve(eid, meta, no_fetch=no_fetch, echo=echo)
        # from here on, the one read is spent
        try:
            r = lw.score(w, export_dir=str(exports), now=now, s=s)
            after = lw.pages_digest(exports)
        except Exception as err:  # noqa: BLE001 - after the reservation every failure is the spent REFUSED line
            raise SpentRefused(f"after the reservation ({os.path.relpath(held)}), the score stopped: "
                               f"{'' if isinstance(err, lw.WindowRefused) else type(err).__name__ + ': '}{err}; the "
                               "reservation stands and the one read is spent (released only by the architect's "
                               "ruling); nothing recorded") from err
    try:
        sha_after, sides_after = copy_state(path)
    except ReadRefused as err:
        raise SpentRefused(f"after the reservation ({os.path.relpath(held)}): {err}; the reservation stands and the "
                           "one read is spent; nothing recorded") from err
    if after["digest"] != pages["digest"] or sha_after != sha or sides_after:
        raise SpentRefused(f"after the reservation ({os.path.relpath(held)}): "
                           + ("the pages changed during the read" if after["digest"] != pages["digest"] else
                              "the copy changed during the read" if sha_after != sha else
                              f"a sidecar appeared beside the copy ({', '.join(sides_after)})")
                           + "; the reservation stands and the one read is spent; nothing recorded")
    if r["match_ids"] != w["members"] or r.get(lw.LAST_MEMBER) != w.get(lw.LAST_MEMBER):
        raise SpentRefused(f"after the reservation ({os.path.relpath(held)}): the score's window is not the read's; "
                           "the reservation stands and the one read is spent; nothing recorded")
    return result(code, e, w, r, sha, pages, word, fp, now, held)


def _code_sha() -> str | None:
    import subprocess
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=_reg().ROOT, capture_output=True, text=True,
                              timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def result(code, e, w, r, sha, pages, word, fp, now, held) -> dict:
    """The run record's `result` (the module docstring), JSON text throughout."""
    a = r["audit"]
    last_id, last_ko = r[lw.LAST_MEMBER]
    out = {"command": COMMAND, "code": code, "n": r["n"], "ll_candidate": r["ll_candidate"],
           "ll_close": r["ll_close"], "verdict": r["verdict"],
           "members_in_order": list(r["match_ids"]),
           "confirmation_opens_after": {"kickoff": _iso(last_ko), "match_id": last_id},
           "took_no_slot": [{"match_id": i, "kickoff": _iso(ko), "cause": c} for i, ko, c in r[lw.TOOK_NO_SLOT]],
           "audit": _jsonable(a), "audit_lines": lw.audit_lines(code, a),
           "frozen_constants": dict(r["constants"]), "ruled_exclusions": _jsonable(e.get(lw.RULED_FIELD) or []),
           "copy_sha256": sha, "pages": dict(pages), "architect_word": word, "window_fingerprint": fp,
           "read_clock": _iso(now), "first_allowed_date": first_allowed(w).isoformat(),
           "reservation": os.path.relpath(held, _reg().ROOT)}
    try:
        json.dumps(out, allow_nan=False)
    except (TypeError, ValueError) as err:
        raise SpentRefused(f"the run record could not be written as JSON ({err}); the reservation stands and the one "
                           "read is spent; nothing recorded") from err
    return out


def run_lines(res: dict) -> list[str]:
    """The read's console: both figures, unrounded, the computed verdict, the audit lines and the accounting by cause.
    The architect reads this, then rules (B1)."""
    from collections import Counter
    causes = Counter(x["cause"] for x in res["took_no_slot"])
    return ([f"  n={res['n']} · candidate mean log-loss {res['ll_candidate']!r} · the close's {res['ll_close']!r} · "
             "PASS only when the candidate's is strictly below (a tie REJECTS)",
             f"  the opening (447 C1): the 60th member, match {res['confirmation_opens_after']['match_id']}, kicks off "
             f"{res['confirmation_opens_after']['kickoff']}",
             f"  reached and took no slot (447 B2(e)), by id in the run record: {len(res['took_no_slot'])}"
             + ("" if not causes else " — " + ", ".join(f"{k} {v}" for k, v in sorted(causes.items())))]
            + res["audit_lines"]
            + [f"  VERDICT (computed; the architect rules, then --record-verdict): {res['verdict']}"])


def record(code: str, res: dict) -> dict:
    reg = _reg()
    return reg.record_run(lw.DECLARATION_IDS[code], list(res["members_in_order"]), res, reg.LEDGER, reg.IDS_DIR)


# --------------------------------------------------------------------------------------- the verdict (B1) --

def record_verdict(code, verdict, ruling) -> dict:
    """B1: refused unless the run is recorded (by this command: its computed verdict in the run record), no verdict
    is recorded yet, the ruling is given, and the word given equals the computed one. Then registry.record_verdict
    (PASS: confirming; REJECT: closed)."""
    reg = _reg()
    c = (code or "").strip().upper()
    if c not in CODES:
        raise ReadRefused(f"--code {code!r}: not one of the five leagues windows; nothing recorded")
    eid = lw.DECLARATION_IDS[c]
    if not ruling or not str(ruling).strip():
        raise ReadRefused("--ruling is required: the architect's words, verbatim; nothing recorded")
    v = (verdict or "").strip().upper()
    if v not in VERDICT_WORDS:
        raise ReadRefused(f"--record-verdict {verdict!r}: PASS or REJECT; nothing recorded")
    try:
        e = lw.declaration(c)
    except lw.WindowRefused as err:
        raise ReadRefused(f"{eid}: {err}") from err
    if not e or not e.get("run"):
        raise ReadRefused(f"{eid}: no run recorded: a verdict needs the one read; nothing recorded")
    if e.get("verdict"):
        raise ReadRefused(f"{eid}: a verdict is already recorded; nothing recorded")
    computed = ((e["run"].get("result") or {}).get("verdict") or "").upper()
    if (e["run"].get("result") or {}).get("command") != COMMAND or computed not in VERDICT_WORDS:
        raise ReadRefused(f"{eid}: the run record carries no computed verdict of {COMMAND}; nothing recorded")
    if v != computed:
        raise ReadRefused(f"{eid}: the word given is {v}, the computed verdict is {computed} (B1: refused unless "
                          "the word equals the computed one); nothing recorded")
    try:
        return reg.record_verdict(eid, v, str(ruling), reg.LEDGER)
    except reg.RegistryError as err:
        raise ReadRefused(f"{eid}: {err}; nothing recorded") from err
