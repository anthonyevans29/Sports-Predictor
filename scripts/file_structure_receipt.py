"""
THE FILE STRUCTURE RECEIPT (DEV 4, Lane D; the brief of addendum 518 item 5; Refs #105, #838), READ-ONLY.

WHAT IT IS FOR. The architect's blocks run it on the laptop over files this session never sees: MoneyPuck's files
(reopened by the operator, addendum 517; their structure read by block before the depth probe, 517 item 2(f)) and
the tennis archive (reopened, addendum 518 item 2). Counts and structure only leave the laptop (517 item 2(d), 518
item 2(b)). So the script ASSUMES NO COLUMN NAME (law 1): every name it prints is read from the file's own header.

WHAT IT READS. One or more PATHs, each a file or a folder:
- a FILE is read by its name: *.zip as a zip archive, *.gz as a gzip stream of CSV text, anything else as CSV text.
- a FOLDER lists its files directly inside it (every subfolder too with --recursive), in name order, and reads those
  named *.csv, *.csv.gz or *.zip (case ignored). Every other file is named as SKIPPED and not opened.
- in a ZIP, each member named *.csv is its own entry (ARCHIVE!MEMBER); every other member is named as SKIPPED and
  not read. Nothing is extracted.
- the FIRST RECORD of each CSV is its header. The text is decoded with --encoding (default utf-8-sig) and split with
  --delimiter (default a comma). Neither is guessed.

WHAT IT PRINTS, per CSV (the rules line before the first file states every rule below):
- the name, the size in bytes and the sha256 of the bytes on disk (for a zip member, the archive's size and sha256);
  for a .gz file or a zip member, also the size and sha256 of the decompressed CSV bytes it read;
- the row count (records after the header; a blank record is counted apart and is not a row), the column count, the
  columns in order, and the ragged rows (a field count other than the header's);
- per column: the null share (a cell exactly one of NULL_TOKENS), the empty share ('' or whitespace only), the absent
  share (a ragged row too short to reach it), the kind of its other cells (KINDS), the distinct count of its other
  cells (exact, on the raw text, up to --distinct-cap), and the minimum and maximum ONLY for an int, float, date or
  datetime column;
- for a column named with --vocab (the header's exact text; repeatable): each distinct raw value with its count,
  null and empty cells included, the most frequent first, at most --vocab-max values, then the rest as one count.

WHAT IT NEVER DOES. It never prints a row, nor a value of a column that was not named, save the minimum and maximum
of a numeric or date column (the brief names those). An error line names the record number and the error's class,
never the bytes. A header whose cells parse as a number or a date may be a data row: its names are WITHHELD and the
columns print by position. It writes nothing: no file, no cache, no temporary file.

REFUSED, exit 2, before any file is opened (law 5): a PATH, or a file found inside a folder, any part of whose path,
as given or resolved (a symlink followed), is named data (case ignored: the laptop's filesystem ignores case; the
tennis receipt's rule, addendum 308 item 1(c)), or that resolves under the checkout's data/ (sp_common's rule,
written out here so the script imports nothing of deploy/). Also refused: no PATH, a --delimiter that is not one
character, an --encoding Python does not know, a --vocab-max or --distinct-cap below 1.

EXIT: 0 when every CSV entry was read whole; 1 when a PATH does not exist, a file or member could not be read whole
(a decode error, a csv error, a truncated or corrupt .gz or .zip, an encrypted member, an OS error), or no CSV entry
was found at all; the others are still read and printed. 2 on a refusal, nothing read.

Python 3.10 is the floor (CONTRIBUTING.md): stdlib only, no PEP 701 f-strings.
"""
from __future__ import annotations

import argparse
import codecs
import csv
import gzip
import hashlib
import io
import os
import re
import sys
import zipfile
import zlib
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

_INT = re.compile(r"[+-]?\d+")
_FLOAT = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_DATETIME = re.compile(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?"
                       r"(Z|[+-]\d{2}:\d{2})?")
_BOOLS = frozenset({"true", "false"})

RULES = ("RULES: the first record is the header; null = a cell exactly one of " + ", ".join(NULL_TOKENS)
         + "; empty = '' or whitespace only; absent = a ragged row too short to reach the column; a kind and a "
           "distinct count are of the other cells (kind on the cell stripped, distinct on its raw text); kinds "
           "bool (true/false, case ignored), int, float, date (YYYY-MM-DD), datetime (ISO 8601, T or space, "
           "Z or +hh:mm, all with or all without a zone), text (anything else, or a mix), none (no other cell); "
           "no MM/DD or DD/MM date is read as a date; min and max print for int, float, date and datetime only; "
           "a vocab lists the raw values of a column named with --vocab, null and empty cells included")


class Refused(Exception):
    """A refused run: exit 2, nothing opened."""


# --------------------------------------------------------------------------
# Refusal (law 5)
# --------------------------------------------------------------------------


def data_refusal(raw: str | os.PathLike, root: Path = ROOT) -> str | None:
    """The REFUSED line for a path under a data/ directory, else None. Any part named data, case ignored, as given
    or resolved (a symlink followed); and anything that resolves under the checkout's data/ (sp_common's rule)."""
    p = Path(raw).expanduser()
    try:
        resolved = p.resolve()
    except (RuntimeError, OSError) as e:            # a symlink loop, an unknown ~user: refused, never a trace
        return "REFUSED: {} cannot be resolved ({})".format(raw, type(e).__name__)
    if any(part.casefold() == "data" for part in list(p.parts) + list(resolved.parts)):
        return "REFUSED: {} is under a data/ directory (law 5); name a path outside it".format(raw)
    data = (root / "data").resolve()
    if resolved == data or data in resolved.parents:
        return "REFUSED: {} resolves under the checkout's data/ ({}) (law 5)".format(raw, data)
    return None


# --------------------------------------------------------------------------
# Targets
# --------------------------------------------------------------------------


@dataclass
class Target:
    path: Path
    shown: str


def _readable_name(name: str) -> bool:
    low = name.lower()
    return any(low.endswith(s) for s in READ_SUFFIXES)


def collect(raws: list[str], recursive: bool) -> tuple[list[Target], list[str], list[str]]:
    """(the files to read, the missing paths, the files skipped). Lists folders; opens no file. Raises Refused
    on the first path under data/, before anything is opened."""
    targets: list[Target] = []
    missing: list[str] = []
    skipped: list[str] = []
    for raw in raws:
        why = data_refusal(raw)
        if why:
            raise Refused(why)
        p = Path(raw).expanduser()
        if p.is_dir():
            found: list[tuple[str, Path]] = []
            if recursive:
                for dirpath, dirnames, filenames in os.walk(p):
                    dirnames.sort()
                    for d in dirnames:
                        why = data_refusal(Path(dirpath) / d)
                        if why:
                            raise Refused(why)
                    for fn in sorted(filenames):
                        fp = Path(dirpath) / fn
                        found.append((str(fp.relative_to(p)), fp))
            else:
                for fn in sorted(os.listdir(p)):
                    fp = p / fn
                    if fp.is_dir():
                        continue
                    found.append((fn, fp))
            for rel, fp in found:
                why = data_refusal(fp)
                if why:
                    raise Refused(why)
                shown = "{}/{}".format(raw.rstrip("/\\"), rel)
                if _readable_name(fp.name):
                    targets.append(Target(fp, shown))
                else:
                    skipped.append(shown)
        elif p.exists():
            targets.append(Target(p, raw))
        else:
            missing.append(raw)
    return targets, missing, skipped


# --------------------------------------------------------------------------
# Per-column statistics
# --------------------------------------------------------------------------


def _parse_datetime(s: str):
    m = _DATETIME.fullmatch(s)
    if not m:
        return None
    y, mo, d, hh, mm, ss, frac, tz = m.groups()
    try:
        micro = int((frac or "0").ljust(6, "0"))
        tzinfo = None
        if tz == "Z":
            tzinfo = timezone.utc
        elif tz:
            sign = 1 if tz[0] == "+" else -1
            off = timedelta(hours=int(tz[1:3]), minutes=int(tz[4:6]))
            if off >= timedelta(hours=24):
                return None
            tzinfo = timezone(sign * off)
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
    if len(s) != 8 or not s.isdigit():
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
    distinct: set | None = field(default_factory=set)
    vocab_counts: Counter | None = None
    vocab_capped: bool = False
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
        if self.vocab_counts is not None and not self.vocab_capped:
            self.vocab_counts[raw] += 1
            if len(self.vocab_counts) > self.distinct_cap:
                self.vocab_capped = True
                self.vocab_counts = None
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
            if _INT.fullmatch(s):
                self._track("int", int(s), s)
                if self.all_yyyymmdd and not _yyyymmdd(s):
                    self.all_yyyymmdd = False
            else:
                self.can_int = False
        if self.can_float:
            if _FLOAT.fullmatch(s):
                self._track("float", float(s), s)
            else:
                self.can_float = False
        if self.can_date:
            d = _parse_date(s)
            if d is None:
                self.can_date = False
            else:
                self._track("date", d, s)
        if self.can_datetime:
            dt = _parse_datetime(s)
            if dt is None:
                self.can_datetime = False
            else:
                aware = dt.tzinfo is not None
                self.tz_seen.add(aware)
                if len(self.tz_seen) > 1:
                    self.can_datetime = False       # aware and naive mixed: no order between them; text
                else:
                    self._track("datetime", dt, s)

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
    header: list[str] | None = None
    rows: int = 0
    blank: int = 0
    ragged: int = 0
    columns: list[ColumnStats] = field(default_factory=list)
    error: str | None = None
    bytes_read: int = 0
    sha_read: str = ""


def _error_text(e: BaseException, record: int, encoding: str) -> str:
    """The error's class and, where the message carries no content of the file, its message. Never the bytes."""
    where = "at record {}".format(record)
    if isinstance(e, UnicodeError):     # text is decoded ahead by chunks: the fault is at or after that record
        return "{}, or after it ({}; encoding {})".format(where, type(e).__name__, encoding)
    if isinstance(e, csv.Error):
        return "{} (csv.Error: {})".format(where, e)
    return "{} ({})".format(where, type(e).__name__)


def read_csv(raw: IO[bytes], encoding: str, delimiter: str, vocab: set[str], distinct_cap: int) -> CsvResult:
    """Read one CSV stream whole. Every record is counted; no record is kept."""
    r = CsvResult()
    hr = HashingReader(raw)
    record = 0
    try:
        text = io.TextIOWrapper(io.BufferedReader(hr, CHUNK), encoding=encoding, newline="")
        reader = csv.reader(text, delimiter=delimiter)
        for rec in reader:
            record += 1
            if r.header is None:
                r.header = rec
                r.columns = [ColumnStats(name, vocab=name in vocab, distinct_cap=distinct_cap) for name in rec]
                continue
            if not rec:
                r.blank += 1
                continue
            r.rows += 1
            cols = r.columns
            n = len(cols)
            if len(rec) != n:
                r.ragged += 1
            for i, c in enumerate(cols):
                if i < len(rec):
                    c.add(rec[i])
                else:
                    c.absent()
        # The reader stops at the decoder's end: drain whatever is left so a trailing corruption is still seen.
        while text.read(CHUNK):
            pass
    except (UnicodeError, csv.Error, OSError, EOFError, zipfile.BadZipFile, zlib.error, RuntimeError,
            NotImplementedError, ValueError) as e:
        r.error = _error_text(e, record + 1, encoding)
    r.bytes_read = hr.n
    r.sha_read = hr.sha.hexdigest()
    return r


# --------------------------------------------------------------------------
# Printing
# --------------------------------------------------------------------------


def _share(n: int, d: int) -> str:
    return "{:.1f}%".format(100.0 * n / d) if d else "n/a"


def header_withheld(header: list[str]) -> int:
    """How many header cells parse as a number or a date: >0 and the header may be a data row."""
    k = 0
    for h in header:
        s = h.strip()
        if s and (_FLOAT.fullmatch(s) or _parse_date(s) or _parse_datetime(s)):
            k += 1
    return k


def print_csv(r: CsvResult, out: Callable[[str], None], vocab_max: int) -> None:
    if r.header is None:
        if r.error is None:
            out("  rows 0 · columns 0 (the file holds no record, not even a header)")
        return
    n = len(r.header)
    out("  rows {} · columns {} · blank records {} · ragged rows {}".format(r.rows, n, r.blank, r.ragged))
    withheld = header_withheld(r.header)
    if withheld:
        out("  HEADER WITHHELD: {} of {} header cells parse as a number or a date, so the first record may be a "
            "data row; columns print by position".format(withheld, n))
    seen = Counter(r.header)
    dups = sorted(h for h, c in seen.items() if c > 1)
    if dups and not withheld:
        out("  DUPLICATE column names: {}".format(", ".join(repr(h) for h in dups)))
    for i, c in enumerate(r.columns, 1):
        name = "#{}".format(i) if withheld else repr(c.name)
        if not withheld and not c.name.strip():
            name += " (blank name)"
        kind = c.kind
        bits = ["COL {} {}".format(i, name), "kind " + kind]
        if kind == "int" and c.all_yyyymmdd:
            bits[-1] += " (every value is 8 digits and a valid YYYYMMDD date)"
        if kind == "datetime":
            bits[-1] += " (with a zone)" if True in c.tz_seen else " (no zone)"
        bits += ["null " + _share(c.n_null, r.rows), "empty " + _share(c.n_empty, r.rows)]
        if c.n_absent:
            bits.append("absent " + _share(c.n_absent, r.rows))
        bits.append("distinct " + ("more than {:,} (cap)".format(c.distinct_cap) if c.distinct is None
                                   else str(len(c.distinct))))
        if kind in ("int", "float", "date", "datetime"):
            bits += ["min " + c.lo[kind][1], "max " + c.hi[kind][1]]
        out("  " + " · ".join(bits))
    for i, c in enumerate(r.columns, 1):
        if not c.vocab:
            continue
        label = "#{}".format(i) if withheld else repr(c.name)
        if c.vocab_counts is None:
            out("  VOCAB {}: more than {:,} distinct values (cap); not listed".format(label, c.distinct_cap))
            continue
        items = sorted(c.vocab_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        out("  VOCAB {} ({} distinct, {} cells):".format(label, len(items), sum(c.vocab_counts.values())))
        for v, cnt in items[:vocab_max]:
            out("    {} {}".format(repr(v), cnt))
        rest = items[vocab_max:]
        if rest:
            out("    ... and {} more values ({} cells)".format(len(rest), sum(cnt for _, cnt in rest)))


def sha256_file(p: Path) -> tuple[int, str]:
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


def _entry(shown: str, size_sha: tuple[int, str], r: CsvResult, kind: str, tally: Tally,
           out: Callable[[str], None], vocab_max: int) -> None:
    """kind: 'plain' (the bytes on disk are the CSV), 'gz' (the file's bytes, then the CSV it decompressed to) or
    'member' (the archive's bytes, then the member's decompressed bytes)."""
    out("FILE {}".format(shown))
    if kind == "member":
        out("  archive bytes {} · archive sha256 {}".format(size_sha[0], size_sha[1]))
        out("  member bytes read {} · member sha256 {}".format(r.bytes_read, r.sha_read))
    else:
        out("  bytes {} · sha256 {}".format(size_sha[0], size_sha[1]))
        if kind == "gz":
            out("  decompressed bytes read {} · sha256 {}".format(r.bytes_read, r.sha_read))
    print_csv(r, out, vocab_max)
    if r.header:
        tally.vocab_found.update(c.name for c in r.columns if c.vocab)
    if r.error:
        out("  ERROR: not read whole, {}".format(r.error))
        tally.failed += 1
    else:
        tally.whole += 1


def read_target(t: Target, args, vocab: set[str], tally: Tally, out: Callable[[str], None]) -> None:
    name = t.path.name.lower()
    try:
        size_sha = sha256_file(t.path)
    except OSError as e:
        out("FILE {}".format(t.shown))
        out("  ERROR: not read whole, before the first record ({})".format(type(e).__name__))
        tally.failed += 1
        return
    if name.endswith(".zip"):
        try:
            zf = zipfile.ZipFile(t.path)
        except (zipfile.BadZipFile, OSError, ValueError, NotImplementedError, EOFError) as e:
            out("FILE {}".format(t.shown))
            out("  bytes {} · sha256 {}".format(*size_sha))
            out("  ERROR: not read whole, not a readable zip archive ({})".format(type(e).__name__))
            tally.failed += 1
            return
        with zf:
            members = [m for m in zf.infolist() if not m.is_dir()]
            csvs = [m for m in members if m.filename.lower().endswith(".csv")]
            for m in members:
                if m not in csvs:
                    out("SKIPPED {}!{} (a zip member not named .csv; not read)".format(t.shown, m.filename))
                    tally.skipped += 1
            if not csvs:
                out("FILE {}".format(t.shown))
                out("  bytes {} · sha256 {}".format(*size_sha))
                out("  ERROR: the archive holds no member named .csv")
                tally.failed += 1
                return
            for m in csvs:
                shown = "{}!{}".format(t.shown, m.filename)
                try:
                    f = zf.open(m)
                except (zipfile.BadZipFile, OSError, RuntimeError, NotImplementedError, ValueError, EOFError) as e:
                    out("FILE {}".format(shown))
                    out("  archive bytes {} · archive sha256 {}".format(*size_sha))
                    out("  ERROR: not read whole, before the first record ({})".format(type(e).__name__))
                    tally.failed += 1
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
    if len(args.delimiter) != 1:
        return "REFUSED: --delimiter must be one character"
    try:
        codecs.lookup(args.encoding)
    except LookupError:
        return "REFUSED: --encoding {!r} is not an encoding Python knows".format(args.encoding)
    if args.vocab_max < 1:
        return "REFUSED: --vocab-max must be 1 or more"
    if args.distinct_cap < 1:
        return "REFUSED: --distinct-cap must be 1 or more"
    return None


def main(argv: list[str] | None = None, out: Callable[[str], None] = print) -> int:
    args = _parser().parse_args(argv)
    why = _check_args(args)
    if why:
        out(why)
        return 2
    out("THE FILE STRUCTURE RECEIPT (read-only; no row printed; values only of the columns named with --vocab, and the "
        "min and max of numeric and date columns; nothing written)")
    try:
        targets, missing, skipped = collect(args.paths, args.recursive)
    except Refused as e:
        out(str(e))
        out("EXIT 2 (refused; no file opened)")
        return 2
    out(RULES)
    out("OPTIONS: encoding {} · delimiter {!r} · distinct cap {:,} · vocab max {} · vocab {}".format(
        args.encoding, args.delimiter, args.distinct_cap, args.vocab_max,
        ", ".join(repr(v) for v in args.vocab) or "none"))
    for name in skipped:
        out("SKIPPED {} (not .csv, .csv.gz or .zip; not opened)".format(name))
    csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))   # a long field is read, not refused: the file is read whole
    vocab = set(args.vocab)
    tally = Tally(skipped=len(skipped))
    for m in missing:
        out("MISSING {} (no such file or folder)".format(m))
        tally.failed += 1
    for t in targets:
        read_target(t, args, vocab, tally, out)
    for v in args.vocab:
        if v not in tally.vocab_found:
            out("VOCAB {!r}: no file read has a column with that exact name".format(v))
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
