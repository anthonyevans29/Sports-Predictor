"""
THE FILE STRUCTURE RECEIPT (DEV 4, Lane D; the brief of addendum 518 item 5, ruled by addendum 521 item 6; Refs #105,
#838), READ-ONLY.

WHAT IT IS FOR. The architect's blocks run it on the laptop over files this session never sees: MoneyPuck's files
(reopened by the operator, addendum 517; their structure read by block before the depth probe, 517 item 2(f)) and
the tennis archive (reopened, addendum 518 item 2), kept under logs/sources/ (521 item 6 Q1). Counts and structure
only leave the laptop (517 item 2(d), 518 item 2(b)). So the script ASSUMES NO COLUMN NAME (law 1): every name it
prints is read from the file's own header.

WHAT IT READS. One or more PATHs, each a file or a folder:
- a FILE named as a PATH is read by its name: *.zip as a zip archive, *.gz as a gzip stream of CSV text, anything
  else as CSV text. It must be a regular file (a FIFO or a device is never opened).
- a FOLDER lists what is directly inside it (with --recursive, every subfolder too, in name order) and reads the
  regular files named *.csv, *.csv.gz or *.zip (case ignored). Everything else is named as SKIPPED with its reason
  and not opened: another kind of file, a macOS AppleDouble file (._name), a subfolder without --recursive, a
  symlinked subfolder (never entered). A folder that cannot be listed is an ERROR.
- in a ZIP, each member named *.csv is its own entry (ARCHIVE!MEMBER); every other member, and macOS metadata
  (__MACOSX/, ._name), is named as SKIPPED and not read. Nothing is extracted.
- the FIRST NON-BLANK RECORD of each CSV is its header (blank records before it are counted as blank). The text is
  decoded with --encoding (default utf-8-sig) and split with --delimiter (default a comma), strictly: an unclosed
  quote or a character after a closing quote is a csv error, never a silent merge. Neither option is guessed.

WHAT IT PRINTS, per CSV (the RULES line before the first file states every rule below):
- the name, the size in bytes and the sha256 of the bytes on disk (for a zip member, the archive's size and sha256,
  then the member's); for a .gz file or a zip member, also the size and sha256 of the decompressed CSV bytes read;
- the row count (records after the header; a blank record is counted apart and is not a row), the column count, the
  columns in order, and the ragged rows (a field count other than the header's);
- per column: the null share (a cell exactly one of NULL_TOKENS), the empty share ('' or whitespace only), the absent
  share (a ragged row too short to reach it), the kind of its other cells (KINDS), the distinct count of its other
  cells (exact, on the raw text, up to --distinct-cap, printed as "more than N (cap)" above it), and the minimum and
  maximum ONLY for an int, float, date or datetime column. A share above 0 that rounds to 0.0% prints "<0.1%"; one
  below 100 that rounds to 100.0% prints ">99.9%";
- for a column named with --vocab (the header's exact text; repeatable): each distinct raw value with its count,
  null and empty cells included, the most frequent first, at most --vocab-max values, then the rest as one count.
- a file NOT READ WHOLE prints its ERROR line first, and every figure after it is marked PARTIAL (up to the error).

WHAT IT NEVER DOES. It never prints a row, nor a value of a column that was not named, save the minimum and maximum
of a numeric or date column (the brief's one exception, 521 item 6 Q2). An error line names the record number and the
error's class, never the bytes. A header that may be a data row is WITHHELD and its columns print by position: one
with a cell that parses as a number, a date, a bool or a null token, or a cell whose text recurs as a value in its
own column. A name (a file's, a member's, a column's) prints with its control characters escaped. It writes nothing:
no file, no cache, no temporary file.

REFUSED, exit 2, before any file is opened (law 5; 521 item 6 Q1: "ANY DIRECTORY NAMED data ... read on the path on
disk as given and as resolved"): a PATH, or anything found inside a folder, any part of whose path, as given or
resolved (a symlink followed), is named data (case ignored), or that resolves under the checkout's data/
(sp_common's rule, written out here so the script imports nothing of deploy/). A zip member's name is not a path on
disk and is not refused for holding that word (521 item 6 Q1). Also refused: no PATH, a --delimiter that is not one
character, an --encoding that is not a text encoding Python knows, a --vocab-max or --distinct-cap below 1, and a
PATH that cannot be resolved (an unknown ~user, a symlink loop).

EXIT: 0 when every CSV entry was read whole; 1 when a PATH does not exist or is not a regular file or a folder, a
folder could not be listed, an entry found inside a folder cannot be resolved (a symlink loop; never opened), a file or member could not be read whole (a decode error, a csv error, a NUL character in
the text, a truncated or corrupt .gz or .zip, an encrypted member, an OS error), or no CSV entry was found at all; the
others are still read and printed, and the SUMMARY line always ends the run. 2 on a refusal, nothing opened. An error
found while the bytes are read is placed "at record N, or after it": they are decompressed and decoded ahead of the
reader, by chunks.

Python 3.10 is the floor (CONTRIBUTING.md): stdlib only, no f-strings at all.
"""
from __future__ import annotations

import argparse
import csv
import errno
import gzip
import hashlib
import io
import os
import re
import stat
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import IO, Callable

ROOT = Path(__file__).resolve().parents[1]

NULL_TOKENS = ("NA", "N/A", "NULL", "null", "None", "NaN", "nan", "\\N")
_NULLS = frozenset(NULL_TOKENS)
KINDS = ("bool", "int", "float", "date", "datetime", "text", "none")
READ_SUFFIXES = (".csv", ".csv.gz", ".zip")
DEFAULT_DISTINCT_CAP = 100_000
DEFAULT_VOCAB_MAX = 200
CHUNK = 1 << 20

_INT = re.compile(r"[+-]?\d+", re.ASCII)
_FLOAT = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?", re.ASCII)
_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})", re.ASCII)
_DATETIME = re.compile(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?"
                       r"(Z|[+-]\d{2}:\d{2})?", re.ASCII)
_BOOLS = frozenset({"true", "false"})

RULES = ("RULES: the first non-blank record is the header, read strictly; null = a cell exactly one of "
         + ", ".join(NULL_TOKENS)
         + "; empty = '' or whitespace only; absent = a ragged row too short to reach the column; shares are of "
           "the rows; a kind and a distinct count are of the other cells (kind on the cell stripped, distinct on "
           "its raw text); kinds bool (true/false, case ignored), int, float (ASCII digits), date (YYYY-MM-DD), "
           "datetime (ISO 8601, T or space, Z or +hh:mm, all with or all without a zone), text (anything else, or "
           "a mix), none (no other cell); no MM/DD or DD/MM date is read as a date; min and max print for int, "
           "float, date and datetime only; a vocab lists the raw values of a column named with --vocab, null and "
           "empty cells included; a header that may be a data row is withheld")


class Refused(Exception):
    """A refused run: exit 2, nothing opened."""


class NulInText(ValueError):
    """A NUL character in the decoded text: an error on every Python (3.10's csv refuses it, 3.11+ would read it)."""


def show(name) -> str:
    """A name as printed: its control and other non-printable characters escaped, so no name can forge a line."""
    return "".join(ch if ch.isprintable() else ch.encode("unicode_escape").decode("ascii") for ch in str(name))


# --------------------------------------------------------------------------
# Refusal (law 5)
# --------------------------------------------------------------------------


def unresolvable(raw) -> str | None:
    """The error's class name when a path cannot be resolved (an unknown ~user; a symlink loop, read the same way on
    every Python: 3.10's resolve raises, 3.13's does not, so os.stat's ELOOP is checked too), else None."""
    try:
        Path(raw).expanduser().resolve()
    except (RuntimeError, OSError) as e:
        return type(e).__name__
    try:
        os.stat(Path(raw).expanduser())
    except OSError as e:
        if e.errno == errno.ELOOP:
            return "a symlink loop"
    except (RuntimeError, ValueError) as e:
        return type(e).__name__
    return None


def data_refusal(raw, root: Path = ROOT) -> str | None:
    """The REFUSED line for a path under a data/ directory, else None. Any part named data, case ignored, as given
    or resolved (a symlink followed); and anything that resolves under the checkout's data/ (sp_common's rule).
    A path that cannot be resolved is refused too: it cannot be shown to lie outside data/."""
    why = unresolvable(raw)
    if why:
        return "REFUSED: {} cannot be resolved ({})".format(show(raw), why)
    p = Path(raw).expanduser()
    resolved = p.resolve()
    if any(part.casefold() == "data" for part in list(p.parts) + list(resolved.parts)):
        return "REFUSED: {} is under a data/ directory (law 5); name a path outside it".format(show(raw))
    data = (root / "data").resolve()
    if resolved == data or data in resolved.parents:
        return "REFUSED: {} resolves under the checkout's data/ ({}) (law 5)".format(show(raw), data)
    return None


# --------------------------------------------------------------------------
# Targets
# --------------------------------------------------------------------------


@dataclass
class Target:
    path: Path
    shown: str


@dataclass
class Collected:
    targets: list = field(default_factory=list)     # Target
    failed: list = field(default_factory=list)      # (shown, why): exit 1
    skipped: list = field(default_factory=list)     # (shown, why)


def _readable_name(name: str) -> bool:
    low = name.lower()
    return any(low.endswith(s) for s in READ_SUFFIXES)


def _is_appledouble(name: str) -> bool:
    return name.startswith("._")


def _refuse(p) -> None:
    why = data_refusal(p)
    if why:
        raise Refused(why)


def _join(raw: str, rel: str) -> str:
    return raw if rel in ("", ".") else os.path.join(raw, rel)


def collect(raws: list[str], recursive: bool) -> Collected:
    """Lists folders; opens no file. Raises Refused on the first path under data/, before anything is opened. A
    PATH named by the caller that cannot be resolved is refused; an entry found inside a folder that cannot be
    resolved (a symlink loop) is an ERROR and is never opened."""
    c = Collected()

    def entry_ok(fp, shown) -> bool:
        why = unresolvable(fp)
        if why:
            c.failed.append((shown, "cannot be resolved ({}); not opened".format(why)))
            return False
        _refuse(fp)
        return True
    for raw in raws:
        _refuse(raw)
        p = Path(raw).expanduser()
        try:
            st = os.stat(p)
        except FileNotFoundError:
            c.failed.append((show(raw), "MISSING (no such file or folder)"))
            continue
        except OSError as e:
            c.failed.append((show(raw), "not read ({})".format(type(e).__name__)))
            continue
        if stat.S_ISREG(st.st_mode):
            c.targets.append(Target(p, show(raw)))
            continue
        if not stat.S_ISDIR(st.st_mode):
            c.failed.append((show(raw), "not a regular file or a folder; not opened"))
            continue
        found: list = []                             # (rel, path)
        if recursive:
            def onerror(e, raw=raw, p=p):
                rel = os.path.relpath(e.filename, p) if getattr(e, "filename", None) else "."
                c.failed.append((show(_join(raw, rel)), "a folder that could not be listed ({})".format(
                    type(e).__name__)))
            for dirpath, dirnames, filenames in os.walk(p, onerror=onerror):
                dirnames.sort()
                for d in list(dirnames):
                    dp = Path(dirpath) / d
                    shown_d = show(_join(raw, str(dp.relative_to(p))))
                    if not entry_ok(dp, shown_d):
                        continue
                    if os.path.islink(dp):              # False on any error: never a traceback
                        c.skipped.append((shown_d, "a symlinked folder; not entered"))
                for fn in sorted(filenames):
                    fp = Path(dirpath) / fn
                    found.append((str(fp.relative_to(p)), fp))
        else:
            try:
                names = sorted(os.listdir(p))
            except OSError as e:
                c.failed.append((show(raw), "a folder that could not be listed ({})".format(type(e).__name__)))
                continue
            for fn in names:
                fp = p / fn
                if not entry_ok(fp, show(_join(raw, fn))):
                    continue
                try:
                    is_dir = fp.is_dir()
                except OSError:
                    is_dir = False
                if is_dir:
                    c.skipped.append((show(_join(raw, fn)), "a subfolder; not entered without --recursive"))
                    continue
                found.append((fn, fp))
        for rel, fp in found:
            shown = show(_join(raw, rel))
            if not entry_ok(fp, shown):
                continue
            if _is_appledouble(fp.name):
                c.skipped.append((shown, "macOS AppleDouble metadata; not opened"))
                continue
            if not _readable_name(fp.name):
                c.skipped.append((shown, "not .csv, .csv.gz or .zip; not opened"))
                continue
            try:
                regular = stat.S_ISREG(os.stat(fp).st_mode)
            except OSError as e:
                c.failed.append((shown, "not read ({})".format(type(e).__name__)))
                continue
            if not regular:
                c.skipped.append((shown, "not a regular file; not opened"))
                continue
            c.targets.append(Target(fp, shown))
    return c


# --------------------------------------------------------------------------
# Per-column statistics
# --------------------------------------------------------------------------


def _num_key(s: str) -> tuple:
    """An exact order key for a token _FLOAT admits, with no limit on the exponent (#1125: decimal.Decimal refuses an
    exponent past its implementation's bound, so 1e99999999999999999999 read as an error). The value is
    sign x 0.d1d2... x 10^E: zero is (1,); a positive (2, E, digits); a negative (0, -E, its digits each as 9 - d,
    closed by ':', which sorts after every digit, so a longer magnitude sorts first)."""
    t = s.strip()
    neg = t.startswith("-")
    t = t.lstrip("+-")
    mant, _, exp = t.partition("e") if "e" in t else t.partition("E")
    whole, _, frac = mant.partition(".")
    digits = (whole + frac).lstrip("0")
    if not digits.rstrip("0"):
        return (1,)
    lead = len((whole + frac)) - len(digits)               # zeros stripped from the front
    e = int(exp or "0") + len(whole) - lead                # 0.d1d2... x 10^e
    digits = digits.rstrip("0")
    if not neg:
        return (2, e, digits)
    return (0, -e, "".join(str(9 - int(ch)) for ch in digits) + ":")


def _datetime_parts(s: str):
    """(datetime to the microsecond, the fraction's digits past the sixth, trailing zeros stripped), or None. Any
    number of fractional digits is ISO 8601 (nanosecond exports among them); the pair orders exactly (#1125)."""
    m = _DATETIME.fullmatch(s)
    if not m:
        return None
    frac = m.group(7) or ""
    dt = _datetime_of(m, frac[:6])
    return None if dt is None else (dt, frac[6:].rstrip("0"))


def _parse_datetime(s: str):
    parts = _datetime_parts(s)
    return None if parts is None else parts[0]


def _datetime_of(m, frac6: str):
    y, mo, d, hh, mm, ss, _frac, tz = m.groups()
    try:
        micro = int((frac6 or "0").ljust(6, "0"))
        tzinfo = None
        if tz == "Z":
            tzinfo = timezone.utc
        elif tz:
            oh, om = int(tz[1:3]), int(tz[4:6])
            if oh > 23 or om > 59:
                return None
            off = timedelta(hours=oh, minutes=om)
            tzinfo = timezone(off if tz[0] == "+" else -off)
        return datetime(int(y), int(mo), int(d), int(hh), int(mm), int(ss or 0), micro, tzinfo=tzinfo)
    except ValueError:
        return None


def _parse_date(s: str):
    m = _DATE.fullmatch(s)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _yyyymmdd(s: str) -> bool:
    if len(s) != 8 or not (s.isascii() and s.isdigit()):
        return False
    try:
        date(int(s[:4]), int(s[4:6]), int(s[6:]))
    except ValueError:
        return False
    return True


@dataclass
class ColumnStats:
    name: str
    vocab: bool = False
    distinct_cap: int = DEFAULT_DISTINCT_CAP
    n_null: int = 0
    n_empty: int = 0
    n_absent: int = 0
    n_values: int = 0
    can_bool: bool = True
    can_int: bool = True
    can_float: bool = True
    can_date: bool = True
    can_datetime: bool = True
    all_yyyymmdd: bool = True
    tz_seen: set = field(default_factory=set)      # {True, False}: aware / naive datetimes seen
    header_hit: bool = False                       # the header's own text seen as a value: kept past any cap
    distinct: set | None = field(default_factory=set)
    vocab_counts: Counter | None = None
    lo: dict = field(default_factory=dict)         # kind -> (value, token)
    hi: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.vocab:
            self.vocab_counts = Counter()

    def _track(self, kind: str, v, token: str) -> None:
        lo = self.lo.get(kind)
        if lo is None or v < lo[0]:
            self.lo[kind] = (v, token)
        hi = self.hi.get(kind)
        if hi is None or v > hi[0]:
            self.hi[kind] = (v, token)

    def absent(self) -> None:
        self.n_absent += 1

    def add(self, raw: str) -> None:
        if raw == self.name:
            self.header_hit = True
        if self.vocab_counts is not None:
            self.vocab_counts[raw] += 1
            if len(self.vocab_counts) > self.distinct_cap:
                self.vocab_counts = None             # over the cap: freed, printed as "more than CAP"
        if raw in _NULLS:
            self.n_null += 1
            return
        s = raw.strip()
        if not s:
            self.n_empty += 1
            return
        self.n_values += 1
        if self.distinct is not None:
            self.distinct.add(raw)
            if len(self.distinct) > self.distinct_cap:
                self.distinct = None                # over the cap: freed, printed as "more than CAP"
        if self.can_bool and s.lower() not in _BOOLS:
            self.can_bool = False
        if self.can_int:
            v = None
            if _INT.fullmatch(s):
                try:
                    v = int(s)
                except ValueError:                  # past the interpreter's int digit limit: not read as an int
                    v = None
            if v is None:
                self.can_int = False
            else:
                self._track("int", v, s)
                if self.all_yyyymmdd and not _yyyymmdd(s):
                    self.all_yyyymmdd = False
        if self.can_float:
            if _FLOAT.fullmatch(s):
                self._track("float", _num_key(s), s)    # exact: 1e309 and 2e309 stay apart, as do 2**53 and 2**53+1
            else:
                self.can_float = False
        if self.can_date:
            d = _parse_date(s)
            if d is None:
                self.can_date = False
            else:
                self._track("date", d, s)
        if self.can_datetime:
            parts = _datetime_parts(s)
            if parts is None:
                self.can_datetime = False
            else:
                dt = parts[0]
                aware = dt.tzinfo is not None
                self.tz_seen.add(aware)
                if len(self.tz_seen) > 1:
                    self.can_datetime = False       # aware and naive mixed: no order between them; text
                else:
                    self._track("datetime", parts, s)

    @property
    def kind(self) -> str:
        if self.n_values == 0:
            return "none"
        for k, ok in (("bool", self.can_bool), ("int", self.can_int), ("float", self.can_float),
                      ("date", self.can_date), ("datetime", self.can_datetime)):
            if ok:
                return k
        return "text"


# --------------------------------------------------------------------------
# Reading one CSV stream
# --------------------------------------------------------------------------


class HashingReader(io.RawIOBase):
    """A read-only byte stream that hashes and counts every byte read through it."""

    def __init__(self, f: IO[bytes]):
        self._f = f
        self.sha = hashlib.sha256()
        self.n = 0

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:
        data = self._f.read(len(b))
        n = len(data)
        b[:n] = data
        self.sha.update(data)
        self.n += n
        return n


@dataclass
class CsvResult:
    header: list | None = None
    rows: int = 0
    blank: int = 0
    ragged: int = 0
    columns: list = field(default_factory=list)
    error: str | None = None
    bytes_read: int = 0
    sha_read: str = ""


def _error_text(e: BaseException, record: int, encoding: str, exact: bool = False) -> str:
    """The error's class and, where the message carries no content of the file, its message. Never the bytes.
    An error raised while the stream is read is placed "at record N, or after it": the bytes are decompressed and
    decoded ahead of the reader, by chunks."""
    where = "at record {}".format(record) if exact else "at record {}, or after it".format(record)
    if isinstance(e, UnicodeError):
        return "{} ({}; encoding {})".format(where, type(e).__name__, show(encoding))
    if isinstance(e, NulInText):
        return "{} (a NUL character in the text)".format(where)
    if isinstance(e, csv.Error):        # CPython's csv messages name the rule broken, never a field's text
        return "{} (csv.Error: {})".format(where, e)
    return "{} ({})".format(where, type(e).__name__)


def _no_nul(lines):
    for line in lines:
        if "\x00" in line:
            raise NulInText()
        yield line


def read_csv(raw: IO[bytes], encoding: str, delimiter: str, vocab: set, distinct_cap: int) -> CsvResult:
    """Read one CSV stream whole. Every record is counted; no record is kept."""
    r = CsvResult()
    hr = HashingReader(raw)
    record = 0          # records the reader has yielded
    busy = False        # True while one yielded record is being counted: an error then is that record's
    try:
        text = io.TextIOWrapper(io.BufferedReader(hr, CHUNK), encoding=encoding, newline="")
        reader = csv.reader(_no_nul(text), delimiter=delimiter, strict=True)
        for rec in reader:
            record += 1
            busy = True
            if not rec or (r.header is None and all(not x.strip() for x in rec)):
                r.blank += 1                    # before the header, a record of blank cells is blank, never a header
            elif r.header is None:
                r.header = rec
                r.columns = [ColumnStats(name, vocab=name in vocab, distinct_cap=distinct_cap) for name in rec]
            else:
                r.rows += 1
                cols = r.columns
                if len(rec) != len(cols):
                    r.ragged += 1
                for i, c in enumerate(cols):
                    if i < len(rec):
                        c.add(rec[i])
                    else:
                        c.absent()
            busy = False
    except Exception as e:      # every failure is reported by class, never as a traceback that could print content
        r.error = _error_text(e, record if busy else record + 1, encoding, exact=busy)
    r.bytes_read = hr.n
    r.sha_read = hr.sha.hexdigest()
    return r


# --------------------------------------------------------------------------
# Printing
# --------------------------------------------------------------------------


def _share(n: int, d: int) -> str:
    if not d:
        return "n/a"
    v = 100.0 * n / d
    s = "{:.1f}%".format(v)
    if n and s == "0.0%":
        return "<0.1%"
    if n < d and s == "100.0%":
        return ">99.9%"
    return s


def _looks_like_data(s: str) -> bool:
    t = s.strip()
    return bool(t) and (s in _NULLS or t.lower() in _BOOLS or bool(_FLOAT.fullmatch(t))
                        or _parse_date(t) is not None or _parse_datetime(t) is not None)


def header_withheld(r: CsvResult) -> int:
    """How many header cells suggest the header is a data row: a cell that parses as a number, a date, a bool or a
    null token, or whose text recurs as a value in its own column. More than 0 and the names are withheld."""
    k = 0
    for i, h in enumerate(r.header or []):
        if _looks_like_data(h):
            k += 1
        elif i < len(r.columns) and h.strip() and r.columns[i].header_hit:
            k += 1
    return k


def print_csv(r: CsvResult, out: Callable[[str], None], vocab_max: int, part: str) -> None:
    if r.header is None:
        if r.error is None:
            out("  rows 0 · columns 0 (the file holds no record, not even a header; blank records {})".format(
                r.blank))
        else:                                       # the error came before any header: what was counted still prints
            out("  {}rows 0 · columns 0 · blank records {} (no header was reached)".format(part, r.blank))
        return
    n = len(r.header)
    out("  {}rows {} · columns {} · blank records {} · ragged rows {}".format(part, r.rows, n, r.blank, r.ragged))
    withheld = header_withheld(r)
    if withheld:
        out("  HEADER WITHHELD: {} of {} header cells parse as a number, a date, a bool or a null token, or recur as "
            "a value in their own column, so the first record may be a data row; columns print by "
            "position".format(withheld, n))
    seen = Counter(r.header)
    dups = sorted(h for h, c in seen.items() if c > 1)
    if dups and not withheld:
        out("  DUPLICATE column names: {}".format(", ".join(show(repr(h)) for h in dups)))
    for i, c in enumerate(r.columns, 1):
        name = "#{}".format(i) if withheld else show(repr(c.name))
        if not withheld and not c.name.strip():
            name += " (blank name)"
        kind = c.kind
        bits = ["{}COL {} {}".format(part, i, name), "kind " + kind]
        if kind == "int" and c.all_yyyymmdd:
            bits[-1] += " (every value is 8 digits and a valid YYYYMMDD date)"
        if kind == "datetime":
            bits[-1] += " (with a zone)" if True in c.tz_seen else " (no zone)"
        bits += ["null " + _share(c.n_null, r.rows), "empty " + _share(c.n_empty, r.rows)]
        if c.n_absent:
            bits.append("absent " + _share(c.n_absent, r.rows))
        bits.append("distinct " + ("more than {:,} (cap)".format(c.distinct_cap) if c.distinct is None
                                   else str(len(c.distinct))))
        if kind in c.lo:                            # int, float, date, datetime only: KINDS' other kinds track none
            bits += ["min " + show(c.lo[kind][1]), "max " + show(c.hi[kind][1])]
        out("  " + " · ".join(bits))
    for i, c in enumerate(r.columns, 1):
        if not c.vocab:
            continue
        label = "COL {} {}".format(i, "#{}".format(i) if withheld else show(repr(c.name)))
        if c.vocab_counts is None:
            out("  {}VOCAB {}: more than {:,} distinct values, null and empty cells included (cap); not "
                "listed".format(part, label, c.distinct_cap))
            continue
        items = sorted(c.vocab_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        out("  {}VOCAB {} ({} distinct, {} cells):".format(part, label, len(items), sum(c.vocab_counts.values())))
        for v, cnt in items[:vocab_max]:
            out("    {} {}".format(show(repr(v)), cnt))
        rest = items[vocab_max:]
        if rest:
            out("    ... and {} more values ({} cells)".format(len(rest), sum(cnt for _, cnt in rest)))


def sha256_file(p: Path) -> tuple:
    h = hashlib.sha256()
    n = 0
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
            n += len(chunk)
    return n, h.hexdigest()


# --------------------------------------------------------------------------
# One target
# --------------------------------------------------------------------------


@dataclass
class Tally:
    whole: int = 0
    failed: int = 0
    skipped: int = 0
    vocab_found: set = field(default_factory=set)


def _fail(shown: str, why: str, tally: Tally, out: Callable[[str], None], size_sha=None) -> None:
    out("FILE {}".format(shown))
    out("  ERROR: not read whole, {}".format(why))
    if size_sha:
        out("  bytes {} · sha256 {}".format(size_sha[0], size_sha[1]))
    tally.failed += 1


def _entry(shown: str, size_sha: tuple, r: CsvResult, kind: str, tally: Tally,
           out: Callable[[str], None], vocab_max: int) -> None:
    """kind: 'plain' (the bytes on disk are the CSV), 'gz' (the file's bytes, then the CSV it decompressed to) or
    'member' (the archive's bytes, then the member's decompressed bytes). A file not read whole prints its ERROR
    line first and every figure after it as PARTIAL."""
    out("FILE {}".format(shown))
    part = ""
    if r.error:
        out("  ERROR: not read whole, {}".format(r.error))
        part = "PARTIAL (up to the error) "
    if kind == "member":
        out("  archive bytes {} · archive sha256 {}".format(size_sha[0], size_sha[1]))
        out("  {}member bytes read {} · member sha256 {}".format(part, r.bytes_read, r.sha_read))
    else:
        out("  bytes {} · sha256 {}".format(size_sha[0], size_sha[1]))
        if kind == "gz":
            out("  {}decompressed bytes read {} · sha256 {}".format(part, r.bytes_read, r.sha_read))
    print_csv(r, out, vocab_max, part)
    if r.header is not None:
        tally.vocab_found.update(c.name for c in r.columns if c.vocab)
    if r.error:
        tally.failed += 1
    else:
        tally.whole += 1


def _zip_skip_reason(name: str) -> str | None:
    base = name.rsplit("/", 1)[-1]
    if name.startswith("__MACOSX/") or "/__MACOSX/" in name or _is_appledouble(base):
        return "macOS metadata; not read"
    if not name.lower().endswith(".csv"):
        return "a zip member not named .csv; not read"
    return None


def read_target(t: Target, args, vocab: set, tally: Tally, out: Callable[[str], None]) -> None:
    name = t.path.name.lower()
    try:
        size_sha = sha256_file(t.path)
    except OSError as e:
        _fail(t.shown, "before the first record ({})".format(type(e).__name__), tally, out)
        return
    if name.endswith(".zip"):
        try:
            zf = zipfile.ZipFile(t.path)
        except Exception as e:
            _fail(t.shown, "not a readable zip archive ({})".format(type(e).__name__), tally, out, size_sha)
            return
        with zf:
            members = [m for m in zf.infolist() if not m.is_dir()]
            csvs = []
            for m in members:
                why = _zip_skip_reason(m.filename)
                if why:
                    out("SKIPPED {}!{} ({})".format(t.shown, show(m.filename), why))
                    tally.skipped += 1
                else:
                    csvs.append(m)
            if not csvs:
                _fail(t.shown, "the archive holds no member named .csv", tally, out, size_sha)
                return
            for m in csvs:
                shown = "{}!{}".format(t.shown, show(m.filename))
                try:
                    f = zf.open(m)
                except Exception as e:
                    _fail(shown, "before the first record ({})".format(type(e).__name__), tally, out)
                    out("  archive bytes {} · archive sha256 {}".format(*size_sha))
                    continue
                with f:
                    r = read_csv(f, args.encoding, args.delimiter, vocab, args.distinct_cap)
                _entry(shown, size_sha, r, "member", tally, out, args.vocab_max)
        return
    if name.endswith(".gz"):
        with open(t.path, "rb") as raw, gzip.GzipFile(fileobj=raw, mode="rb") as f:
            r = read_csv(f, args.encoding, args.delimiter, vocab, args.distinct_cap)
        _entry(t.shown, size_sha, r, "gz", tally, out, args.vocab_max)
        return
    with open(t.path, "rb") as f:
        r = read_csv(f, args.encoding, args.delimiter, vocab, args.distinct_cap)
    _entry(t.shown, size_sha, r, "plain", tally, out, args.vocab_max)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="file_structure_receipt.py",
        description="Read-only structure receipt for CSV files (plain, .gz, .zip): counts and structure, no row.")
    ap.add_argument("paths", nargs="*", metavar="PATH", help="a file or a folder (never under a data/ directory)")
    ap.add_argument("--vocab", action="append", default=[], metavar="COLUMN",
                    help="list this column's distinct values and counts (the header's exact text; repeatable)")
    ap.add_argument("--vocab-max", type=int, default=DEFAULT_VOCAB_MAX, metavar="N",
                    help="values listed per --vocab column, the most frequent first (default %(default)s)")
    ap.add_argument("--distinct-cap", type=int, default=DEFAULT_DISTINCT_CAP, metavar="N",
                    help="exact distinct count up to N per column, else 'more than N' (default %(default)s)")
    ap.add_argument("--encoding", default="utf-8-sig", help="the text's encoding (default %(default)s)")
    ap.add_argument("--delimiter", default=",", help="the field delimiter, one character (default a comma)")
    ap.add_argument("--recursive", action="store_true", help="read a folder's subfolders too")
    return ap


def _check_args(args) -> str | None:
    if not args.paths:
        return "REFUSED: name at least one PATH (a file or a folder)"
    if len(args.delimiter) != 1 or args.delimiter in ('"', "\r", "\n"):
        return "REFUSED: --delimiter must be one character, not a quote or a line break"
    try:
        io.TextIOWrapper(io.BytesIO(b""), encoding=args.encoding)     # a bytes codec (hex, zlib) refuses here
    except LookupError:
        return "REFUSED: --encoding {} is not a text encoding Python knows".format(show(repr(args.encoding)))
    if args.vocab_max < 1:
        return "REFUSED: --vocab-max must be 1 or more"
    if args.distinct_cap < 1:
        return "REFUSED: --distinct-cap must be 1 or more"
    return None


def main(argv: list | None = None, out: Callable[[str], None] = print) -> int:
    args = _parser().parse_args(argv)
    why = _check_args(args)
    if why:
        out(why)
        return 2
    out("THE FILE STRUCTURE RECEIPT (read-only; no row printed; values only of the columns named with --vocab, and "
        "the min and max of numeric and date columns; nothing written)")
    try:
        found = collect(args.paths, args.recursive)
    except Refused as e:
        out(str(e))
        out("EXIT 2 (refused; no file opened)")
        return 2
    except Exception as e:                              # never a traceback: a traceback could carry content
        out("ERROR: the PATHs could not be listed ({}); no file opened".format(type(e).__name__))
        out("SUMMARY: read whole 0 · not read whole 0 · skipped 0 · EXIT 1")
        return 1
    out(RULES)
    out("OPTIONS: encoding {} · delimiter {} · distinct cap {:,} · vocab max {} · vocab {}".format(
        show(args.encoding), show(repr(args.delimiter)), args.distinct_cap, args.vocab_max,
        ", ".join(show(repr(v)) for v in args.vocab) or "none"))
    old_limit = csv.field_size_limit()
    old_digits = sys.get_int_max_str_digits() if hasattr(sys, "get_int_max_str_digits") else None
    csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))   # a long field is read, not refused: the file is read whole
    if old_digits is not None:
        sys.set_int_max_str_digits(0)                      # a long int cell is read as an int, never a ValueError
    tally = Tally(skipped=len(found.skipped))
    try:
        for shown, why in found.skipped:
            out("SKIPPED {} ({})".format(shown, why))
        for shown, why in found.failed:
            out("ERROR {}: {}".format(shown, why))
            tally.failed += 1
        vocab = set(args.vocab)
        for t in found.targets:
            try:
                read_target(t, args, vocab, tally, out)
            except Exception as e:                      # never a traceback: a traceback could carry content
                _fail(t.shown, "({})".format(type(e).__name__), tally, out)
    finally:
        csv.field_size_limit(old_limit)
        if old_digits is not None:
            sys.set_int_max_str_digits(old_digits)
    for v in args.vocab:
        if v not in tally.vocab_found:
            out("VOCAB {}: no file read has a column with that exact name".format(show(repr(v))))
    code = 0
    if tally.failed:
        code = 1
    elif tally.whole == 0:
        out("NOTHING READ: no CSV entry was found")
        code = 1
    out("SUMMARY: read whole {} · not read whole {} · skipped {} · EXIT {}".format(
        tally.whole, tally.failed, tally.skipped, code))
    return code


if __name__ == "__main__":
    sys.exit(main())
