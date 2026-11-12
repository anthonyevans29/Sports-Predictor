"""
THE NBA INJURY-REPORT PROBE (ARCHITECT 2026-11-05 11:40 ET, addendum 261 item 1(e); 2026-11-12 13:50 ET, addendum 357
item 3; lane availability-record, #830; the lane basketball-market-only, #839, names it). Read-only, zero wiring: no
adapter, no source word, no database, no table, no chain. Nothing it fetches is written anywhere.

261 item 1(e), verbatim: "THE AVAILABILITY RECORD'S NBA FEED (lane availability-record, after the NHL landing feed):
the league's OFFICIAL injury report, published on a fixed daily schedule and stamped by the league — the one pregame
availability source in any sport we cover that carries the publisher's own time. Its probe (read-only, by 11-24) reads
the publication schedule, the document form (a PDF needs a reader dependency; the probe says which) and the fields;
the feed PR follows my ruling on the probe. Kind `injury_status` with the league's own status words in attrs,
verbatim." 261 item 4: "no scraping of a source whose terms forbid it (the probe quotes the terms)".

TWO PHASES (addendum 357 item 3(a), verbatim in part: "a report fetched "marked NOT CLEARED" is a report already
scraped. The script's DEFAULT run is the TERMS PHASE alone [...] then it stops — no index page, no report. The REPORT
PHASE (`--report`, with `--index-url`) is a second block of mine and runs ONLY after my ruling on the terms console."):

  TERMS (the default): the page named by --terms-url and the host's robots.txt as served (--robots-url, else the
    robots.txt of --terms-url's own host, printed as derived). The clauses on automated access, robots, scraping and
    reuse are quoted verbatim with their headings, beside the page's own "last updated" line; robots.txt is printed
    as served. Then it STOPS: no index page and no report is fetched in this phase.
  REPORT (--report, --index-url, --terms-ruling): refused unless --terms-ruling names the ruling on the terms console.
    ONE index read and ONE document (357 item 3(c): "no crawl, no retry loop, a plain honest User-Agent, nothing
    fetched twice"): every report link with the publisher's own stamp as written in the link, the reports per day and
    their times as written, then the newest report fetched for its form (content type, size, sha256, the PDF magic)
    and, with the reader installed, its fields: the document's own header stamp, page 1's opening lines, the column
    headers and the status words exactly as written, with counts. Then the mapping the feed PR would build, printed
    and NOT built (357 item 3(e)).

THE URLS ARE THE ARCHITECT'S (357 item 3(b)): "read from a search on the day I write each block and printed in the
block; none typed from memory, by either of us". This file holds no URL default.

THE READER (357 item 3(d)): pypdf, pure Python, optional, laptop-only, pinned by version and hash in
requirements-probe-pdf.txt (the graph engine's pattern; never requirements.txt), installed by the architect's block.
The fetched document is UNTRUSTED DATA: it is held in memory only, never written, never executed, and parsed by the
reader alone. Without the reader the report phase prints the form and stops (exit 2: the fields are not read).

NOTHING HERE WAS CONFIRMED AGAINST A LIVE ANSWER: this container reaches no nba.com host. The column headers and status
words below are HYPOTHESES (labelled on every line that uses them), printed found or not found; a row that carries
none of the hypothesised status words is printed verbatim so an unseen word surfaces (law 1).

Exit: 0 every read answered; 1 a fetch failed; 2 a read REFUSED (no URL, a report phase without its ruling, nothing
to quote, no reader). The last line: NBA-INJURY-PROBE {json}.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests

ROOT = Path(__file__).resolve().parents[1]

OK, FAILED, REFUSED = 0, 1, 2
TAIL = "NBA-INJURY-PROBE"
# a plain, honest User-Agent (357 item 3(c)): what the client is and that it reads once; no contact detail, no browser
USER_AGENT = "sports-predictor-probe/1 (read-only research probe; one request per URL; no crawl)"
TIMEOUT = 30
READER = "pypdf"
READER_FILE = "requirements-probe-pdf.txt"
# the words an access clause is found by (each matched at a word's start, case-insensitive); the probe quotes, the
# architect reads what the clauses allow
TERMS_WORDS = ("automat", "robot", "scrap", "crawl", "spider", "bot", "harvest", "data mining", "extract", "reuse",
               "re-use", "reproduc", "redistribut", "republish", "commercial", "permission", "license", "licence")
UPDATED = re.compile(r"\b(last\s+(?:updated|modified|revised)|effective\s+(?:date|as\s+of))\b", re.I)
TERMS_QUOTES, QUOTE_CHARS, UPDATED_LINES, ROBOTS_LINES = 60, 700, 5, 400
# HYPOTHESES, never confirmed here (law 1): each is printed found / not found on the run
HEADER_WORDS = ("Game Date", "Game Time", "Matchup", "Team", "Player Name", "Current Status", "Reason")
STATUS_WORDS = ("Out", "Doubtful", "Questionable", "Probable", "Available")
REPORT_HEADER = re.compile(r"Injury\s+Report\s*:\s*(.+)", re.I)
# a stamp as a link may write it: a date YYYY-MM-DD and a clock HH[_:.-MM] AM/PM (read, never assumed: an unparsed link
# is counted and listed)
LINK_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
LINK_TIME = re.compile(r"(?<!\d)(\d{1,2})(?:[_:.\-]?(\d{2}))?\s*([AaPp][Mm])(?![A-Za-z])")
NAME_ROW = re.compile(r"\b[A-Z][A-Za-z'.\-]+(?: [A-Z][A-Za-z'.\-]+)*, [A-Z][A-Za-z'.\-]+")
FIRST_LINES, ROW_SAMPLE, LINE_CHARS = 12, 10, 200


class Out:
    def __init__(self):
        self.lines: list[str] = []

    def __call__(self, line: str = "") -> None:
        self.lines.append(str(line))
        print(line, flush=True)


class Fetcher:
    """One GET per URL, never twice in a run (357 item 3(c)), no retry, the honest User-Agent. Never raises:
    (status or None, headers, body bytes or None, final url, error text or None)."""

    def __init__(self, get=None):
        self.get = get or requests.get
        self.fetched: list[str] = []

    def __call__(self, url: str):
        if url in self.fetched:
            return None, {}, None, url, "REFUSED: this run already fetched this URL (nothing is fetched twice)"
        self.fetched.append(url)
        try:
            r = self.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, allow_redirects=True)
        except Exception as e:                      # noqa: BLE001 - a failed read is reported, never raised
            return None, {}, None, url, f"{type(e).__name__}: {e}"
        body = getattr(r, "content", None)
        err = None if r.status_code == 200 else f"HTTP {r.status_code}"
        if err is None and not body:
            err = "the answer is empty"
        return r.status_code, dict(r.headers or {}), body, getattr(r, "url", url) or url, err


def _text(body: bytes | None) -> str:
    return (body or b"").decode("utf-8", errors="replace")


def page_blocks(page: str) -> list[tuple[str | None, str]]:
    """The page as (heading, sentence) pairs: script/style dropped, every h1-h6 a heading, tags stripped, entities
    unescaped, whitespace folded. The heading is the last one above the sentence, as the page writes it."""
    t = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", page or "")
    t = re.sub(r"\s+", " ", t)                       # the page's own line breaks fold: a block ends only at a tag
    t = re.sub(r"(?is)<h[1-6]\b[^>]*>(.*?)</h[1-6]>",
               lambda m: "\x01\x00H" + re.sub(r"<[^>]+>", " ", m.group(1)) + "\x01", t)
    t = re.sub(r"(?s)<[^>]+>", "\x01", t)
    t = html.unescape(t)
    out, heading = [], None
    for line in t.split("\x01"):
        if line.startswith("\x00H"):
            h = re.sub(r"\s+", " ", line[2:]).strip()
            heading = h or heading
            continue
        for s in re.split(r"(?<=[.!?;])\s+", line):
            s = re.sub(r"\s+", " ", s).strip()
            if s:
                out.append((heading, s))
    return out


def terms_quotes(page: str) -> tuple[list[tuple[str | None, str]], list[str], int]:
    """(the access clauses quoted with their headings, the page's own "last updated" lines, the clauses not printed
    past the cap). A sentence is quoted whole up to QUOTE_CHARS (a cut is marked); nothing is paraphrased."""
    word = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in TERMS_WORDS) + ")", re.I)
    blocks = page_blocks(page)
    hits = [(h, s if len(s) <= QUOTE_CHARS else s[:QUOTE_CHARS] + " [...]") for h, s in blocks if word.search(s)]
    seen, uniq = set(), []
    for h, s in hits:
        if (h, s) not in seen:
            seen.add((h, s))
            uniq.append((h, s))
    updated = []
    for _, s in blocks:
        if UPDATED.search(s) and s not in updated:
            updated.append(s[:QUOTE_CHARS])
    return uniq[:TERMS_QUOTES], updated[:UPDATED_LINES], max(0, len(uniq) - TERMS_QUOTES)


def robots_for(terms_url: str) -> str:
    p = urlsplit(terms_url)
    return f"{p.scheme}://{p.netloc}/robots.txt"


def terms_phase(a, say: Out, fetch: Fetcher) -> tuple[int, dict]:
    """261 item 4 and 357 item 3(a): the terms and robots.txt, quoted; then STOP."""
    if not a.terms_url:
        say("REFUSED: no --terms-url (no URL is typed here: the architect names it in the block, 357 item 3(b)); "
            "nothing fetched")
        return REFUSED, {"refused": "no --terms-url"}
    rec: dict = {"terms_url": a.terms_url}
    worst = OK
    status, hdr, body, final, err = fetch(a.terms_url)
    say(f"TERMS {a.terms_url} · HTTP {status}" + (f" · final URL {final}" if final != a.terms_url else "")
        + (f" · FAILED: {err}" if err else f" · {len(body)} bytes"))
    rec["terms"] = {"http": status, "final_url": final, "error": err}
    if err:
        worst = FAILED
        say("  TERMS NOT READ: the feed is not cleared (261 item 4); the report phase waits on a terms console")
    else:
        quoted, updated, dropped = terms_quotes(_text(body))
        say("  THE PAGE'S OWN DATE LINE(S), verbatim: " + (" | ".join(f'"{u}"' for u in updated) if updated
                                                           else "none found (no 'last updated' / 'effective' line)"))
        if not quoted:
            worst = REFUSED
            say("  NOTHING TO QUOTE: no sentence holds an access word " + str(list(TERMS_WORDS))
                + "; the terms are NOT READ for this feed (the architect reads the page itself)")
        else:
            say(f"  ACCESS CLAUSES QUOTED, verbatim with their headings ({len(quoted)} sentence(s) holding an access "
                f"word {list(TERMS_WORDS)}; the architect reads what they allow):")
            last = object()
            for h, s in quoted:
                if h != last:
                    say(f"    [{h if h else 'no heading above'}]")
                    last = h
                say(f'      "{s}"')
            if dropped:
                say(f"    ... and {dropped} more sentence(s) holding an access word, not printed (cap {TERMS_QUOTES})")
        rec["terms"].update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest(), updated=updated,
                            quoted=[{"heading": h, "text": s} for h, s in quoted], not_printed=dropped)
    robots = a.robots_url or robots_for(a.terms_url)
    status, hdr, body, final, err = fetch(robots)
    say(f"\nROBOTS {robots}" + ("" if a.robots_url else " (derived: --terms-url's own host)") + f" · HTTP {status}"
        + (f" · FAILED: {err}" if err else f" · {len(body)} bytes, as served:"))
    rec["robots"] = {"url": robots, "derived": not a.robots_url, "http": status, "error": err}
    if err:
        worst = max(worst, FAILED)
    else:
        lines = _text(body).splitlines()
        for ln in lines[:ROBOTS_LINES]:
            say(f"  | {ln}")
        if len(lines) > ROBOTS_LINES:
            say(f"  ... and {len(lines) - ROBOTS_LINES} more line(s), not printed (cap {ROBOTS_LINES})")
        rec["robots"].update(lines=len(lines), sha256=hashlib.sha256(body).hexdigest())
    say("\nTERMS PHASE ONLY (addendum 357 item 3(a)): no index page and no report was fetched. The report phase "
        "(--report) runs only after the architect's ruling on this console.")
    return worst, rec


def link_stamp(text: str) -> tuple[str | None, str | None]:
    """(the date YYYY-MM-DD, the clock as written normalized to HH:MM AM/PM) read from a link's file name or text;
    (None, None) when not readable. Read as written: the zone is the document's own, read from its header below."""
    d = LINK_DATE.search(text)
    t = LINK_TIME.search(text[d.end():] if d else text)
    date = f"{d.group(1)}-{d.group(2)}-{d.group(3)}" if d else None
    clock = None
    if t:
        hh, mm = int(t.group(1)), t.group(2) or "00"
        if 1 <= hh <= 12 and int(mm) < 60:
            clock = f"{hh:02d}:{mm} {t.group(3).upper()}"
    return date, clock


def _sort_key(date: str, clock: str | None):
    if clock is None:
        return (date, -1)
    hh, rest = clock.split(":")
    mm, ap = rest.split(" ")
    return (date, (int(hh) % 12 + (12 if ap == "PM" else 0)) * 60 + int(mm))


def index_links(page: str, base: str) -> list[dict]:
    """Every link to a .pdf on the index page, absolute, in page order, once each: its text, file name and stamp."""
    out, seen = [], set()
    for m in re.finditer(r"""(?is)<a\b[^>]*?href\s*=\s*["']([^"']+)["'][^>]*>(.*?)</a>""", page or ""):
        href = html.unescape(m.group(1)).strip()
        if not re.search(r"\.pdf(?:$|[?#])", href, re.I):
            continue
        url = urljoin(base, href)
        if url in seen:
            continue
        seen.add(url)
        text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", m.group(2)))).strip()
        name = urlsplit(url).path.rsplit("/", 1)[-1]
        date, clock = link_stamp(name)
        if date is None:
            date, clock = link_stamp(text)
        out.append({"url": url, "text": text, "file": name, "date": date, "clock": clock})
    return out


def read_pdf_pages(data: bytes) -> list[str]:
    """The reader, isolated (tests substitute it with synthetic page text; no test holds a real report). The bytes are
    UNTRUSTED: parsed in memory by pypdf alone, never written, never executed. ImportError when pypdf is absent."""
    import pypdf                                             # optional: requirements-probe-pdf.txt, the block's install
    reader = pypdf.PdfReader(io.BytesIO(data), strict=False)
    return [(p.extract_text() or "") for p in reader.pages]


def fields_report(pages: list[str], say: Out) -> dict:
    lines = [ln.strip() for p in pages for ln in p.splitlines() if ln.strip()]
    first = [ln.strip() for ln in (pages[0] if pages else "").splitlines() if ln.strip()][:FIRST_LINES]
    say(f"  PAGES {len(pages)} · text lines {len(lines)}")
    stamp = next((REPORT_HEADER.search(ln).group(0) for ln in lines if REPORT_HEADER.search(ln)), None)
    say("  THE DOCUMENT'S OWN STAMP (hypothesis: a line 'Injury Report: ...'): "
        + (f'"{stamp[:LINE_CHARS]}"' if stamp else "NOT FOUND under that form (page 1's opening lines below)"))
    say(f"  PAGE 1, the first {len(first)} text line(s), verbatim:")
    for ln in first:
        say(f"    | {ln[:LINE_CHARS]}")
    p1 = pages[0] if pages else ""
    headers = {w: (w in p1) for w in HEADER_WORDS}
    say("  COLUMN HEADERS (HYPOTHESES, never confirmed here; found on page 1 as written?): "
        + " · ".join(f"{w}: {'found' if v else 'NOT FOUND'}" for w, v in headers.items()))
    counts = Counter()
    for ln in lines:
        for w in STATUS_WORDS:
            if re.search(rf"(?<![A-Za-z]){re.escape(w)}(?![A-Za-z])", ln):
                counts[w] += 1
    say("  STATUS WORDS (HYPOTHESES; lines holding each, case as written): "
        + " · ".join(f"{w}: {counts.get(w, 0)}" for w in STATUS_WORDS))
    bare = [ln for ln in lines if NAME_ROW.search(ln)
            and not any(re.search(rf"(?<![A-Za-z]){re.escape(w)}(?![A-Za-z])", ln) for w in STATUS_WORDS)]
    say(f"  ROWS WITH A 'Last, First' NAME AND NONE OF THE HYPOTHESISED STATUS WORDS: {len(bare)}"
        + (" (the first, verbatim, so an unseen word surfaces):" if bare else ""))
    for ln in bare[:ROW_SAMPLE]:
        say(f"    | {ln[:LINE_CHARS]}")
    return {"pages": len(pages), "lines": len(lines), "stamp": stamp, "first_lines": first, "headers": headers,
            "status_lines": {w: counts.get(w, 0) for w in STATUS_WORDS}, "rows_no_status_word": len(bare)}


MAPPING = (
    "THE MAPPING, printed and NOT built (addendum 357 item 3(e)): one report row -> one availability assertion of kind "
    "`injury_status`; attrs carry the league's own words verbatim (the status word, the reason); source_stamp = the "
    "report's own stamp (its header); identity by the player's name and team as written (the report carries no "
    "player id); the game by the two teams and the US Eastern date, matched to a stored NBA game. A new source word "
    "is a stored-schema change: it ships in the FEED PR with its own new migrate file (354 item 2), after the "
    "architect's ruling on this probe.")


def report_phase(a, say: Out, fetch: Fetcher) -> tuple[int, dict]:
    if not a.terms_ruling or not a.terms_ruling.strip():
        say("REFUSED: --report needs --terms-ruling (the ruling on the terms console that clears the report phase, "
            "addendum 357 item 3(a)); nothing fetched")
        return REFUSED, {"refused": "no --terms-ruling"}
    if not a.index_url:
        say("REFUSED: --report needs --index-url (the architect names it in the block, 357 item 3(b)); nothing fetched")
        return REFUSED, {"refused": "no --index-url"}
    say(f"REPORT PHASE, cleared by: {a.terms_ruling.strip()}")
    rec: dict = {"terms_ruling": a.terms_ruling.strip(), "index_url": a.index_url}
    status, hdr, body, final, err = fetch(a.index_url)
    say(f"INDEX {a.index_url} · HTTP {status}" + (f" · final URL {final}" if final != a.index_url else "")
        + (f" · FAILED: {err}" if err else f" · {len(body)} bytes"))
    rec["index"] = {"http": status, "final_url": final, "error": err}
    if err:
        return FAILED, rec
    links = index_links(_text(body), final)
    parsed = [x for x in links if x["date"]]
    say(f"  REPORT LINKS (.pdf) on the page: {len(links)} · with a date read from the link: {len(parsed)} · "
        f"unread: {len(links) - len(parsed)}")
    for x in [x for x in links if not x["date"]][:ROW_SAMPLE]:
        say(f"    unread stamp: {x['file']!r} (text {x['text'][:80]!r})")
    by_day: dict[str, list] = defaultdict(list)
    for x in parsed:
        by_day[x["date"]].append(x["clock"] or "no clock")
    say("  REPORTS PER DAY and their times, AS WRITTEN in the links (the zone is the document's own, read below):")
    for d in sorted(by_day):
        times = sorted(by_day[d], key=lambda c: _sort_key(d, None if c == "no clock" else c))
        say(f"    {d}: {len(times)} · {', '.join(times)}")
    rec["links"] = {"total": len(links), "dated": len(parsed),
                    "per_day": {d: sorted(v, key=lambda c: _sort_key(d, None if c == "no clock" else c))
                                for d, v in sorted(by_day.items())}}
    if not links:
        say("  NO REPORT LINK on the page: nothing to fetch")
        return FAILED, rec
    pick = max(parsed, key=lambda x: _sort_key(x["date"], x["clock"])) if parsed else links[0]
    why = "the newest by its link's stamp" if parsed else "the first listed (no link carries a readable stamp)"
    say(f"\nONE REPORT ({why}): {pick['url']}")
    status, hdr, data, final, err = fetch(pick["url"])
    ctype = next((v for k, v in hdr.items() if k.lower() == "content-type"), None)
    say(f"  HTTP {status} · content-type {ctype!r}" + (f" · FAILED: {err}" if err else f" · {len(data)} bytes · "
        f"sha256 {hashlib.sha256(data).hexdigest()} · PDF magic {'yes' if data[:5] == b'%PDF-' else 'NO'}"))
    say("  the document is UNTRUSTED DATA: held in memory only, never written, never executed; parsed by the reader "
        "alone")
    rec["report"] = {"url": pick["url"], "file": pick["file"], "http": status, "content_type": ctype, "error": err}
    if err:
        return FAILED, rec
    rec["report"].update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), pdf_magic=data[:5] == b"%PDF-")
    try:
        pages = read_pdf_pages(data)
    except ImportError:
        say(f"  READER NOT INSTALLED ({READER}, {READER_FILE}, installed by the architect's block): the form only; "
            "the fields are NOT READ")
        rec["report"]["reader"] = None
        say("\n" + MAPPING)
        return REFUSED, rec
    except Exception as e:                           # noqa: BLE001 - an unreadable document is reported, never raised
        say(f"  FAILED: the reader could not read the document: {type(e).__name__}: {e}")
        rec["report"]["reader_error"] = f"{type(e).__name__}: {e}"
        return FAILED, rec
    rec["report"]["reader"] = READER
    rec["report"]["fields"] = fields_report(pages, say)
    say("\n" + MAPPING)
    return OK, rec


def refuse_out(path: Path | None) -> str | None:
    """Law 5: never under a data/ directory (compared without case; the checkout's data/ by resolved path too)."""
    if path is None:
        return None
    p = path.expanduser().resolve()
    data = (ROOT / "data").resolve()
    if any(x.casefold() == "data" for x in path.expanduser().parts + p.parts) or p == data or data in p.parents:
        return f"REFUSED: --out {path} is under a data/ directory (law 5); name a path outside it"
    if p.is_dir():
        return f"REFUSED: --out {path} is a directory; name a file"
    if not os.access(p.parent if p.parent.exists() else ROOT, os.W_OK):
        return f"REFUSED: --out {path}: its folder is not writable"
    return None


def main(argv=None, get=None) -> int:
    ap = argparse.ArgumentParser(description="NBA injury-report probe (addendum 261 item 1(e); 357 item 3): read-only, "
                                             "two phases; the terms phase by default")
    ap.add_argument("--terms-url", default=None, help="the terms page, named in the architect's block (no default)")
    ap.add_argument("--robots-url", default=None,
                    help="the robots.txt to read (default: the one at --terms-url's own host, printed as derived)")
    ap.add_argument("--report", action="store_true",
                    help="the REPORT phase: only after the architect's ruling on the terms console")
    ap.add_argument("--index-url", default=None, help="REPORT phase: the index page, named in the block (no default)")
    ap.add_argument("--terms-ruling", default=None,
                    help="REPORT phase: the ruling that cleared it (e.g. 'addendum NNN item M'); required with --report")
    ap.add_argument("--out", type=Path, default=None, help="write the JSON receipt here (never under data/)")
    a = ap.parse_args(argv)
    say = Out()
    refused = refuse_out(a.out)
    if refused:
        say(refused)
        return REFUSED
    phase = "report" if a.report else "terms"
    say(f"NBA INJURY-REPORT PROBE (addendum 261 item 1(e); 357 item 3; lane availability-record, #830) · read-only · "
        f"{phase.upper()} PHASE · {datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ} · User-Agent {USER_AGENT!r}")
    fetch = Fetcher(get)
    if a.report:
        code, rec = report_phase(a, say, fetch)
    else:
        if a.index_url or a.terms_ruling:
            say("REFUSED: --index-url and --terms-ruling belong to the report phase (--report); the terms phase "
                "fetches no index and no report (357 item 3(a)); nothing fetched")
            code, rec = REFUSED, {"refused": "report arguments without --report"}
        else:
            code, rec = terms_phase(a, say, fetch)
    receipt = {"phase": phase, "exit": code, "fetched": fetch.fetched, **rec}
    say(f"\nFETCHED THIS RUN ({len(fetch.fetched)}, each once): " + (" · ".join(fetch.fetched) or "nothing"))
    if a.out:
        try:
            a.out.write_text(json.dumps(receipt, indent=1, default=str))
            say(f"receipt written to {a.out}")
        except OSError as e:
            say(f"FAILED: the receipt was not written: {type(e).__name__}: {e} (the console above is the receipt)")
            code = max(code, FAILED)
            receipt["exit"] = code
    print(f"{TAIL} " + json.dumps(receipt, default=str, sort_keys=True), flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
