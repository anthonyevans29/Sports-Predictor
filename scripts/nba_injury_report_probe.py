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
    robots.txt of --terms-url's own host, printed as derived). The page is read as LINES in page order (each block,
    list item, <br> and heading a line, inline markup kept in place, every line whole); every line holding a word on
    automated access prints in a WINDOW of the page's own lines around it, verbatim (back to a line ending in ":", at
    most WINDOW_BACK lines, and WINDOW_AHEAD on; headings shown), then the reuse and licence windows (capped on the
    console, all in the receipt), beside the page's own date line; no structure is inferred; the --out receipt holds
    every line of the page; robots.txt is printed as served; a redirect prints its final URL and names another host.
    Then it STOPS: no index page and no report is fetched in this phase.
  REPORT (--report, --index-url, --terms-ruling): refused unless --terms-ruling names the ruling on the terms console.
    ONE index read and ONE document (357 item 3(c): "no crawl, no retry loop, a plain honest User-Agent, nothing
    fetched twice"): every report link's file name as written, grouped by day with the clock read from it, the links
    whose date or clock does not read listed; then the newest report fetched for its form (content type, size, sha256,
    the PDF magic) and, with the reader installed, its fields: the document's own header stamp, page 1's opening
    lines, the column headers and the status words exactly as written, with counts. Then the mapping the feed PR would build, printed
    and NOT built (357 item 3(e)).

THE URLS ARE THE ARCHITECT'S (357 item 3(b)): "read from a search on the day I write each block and printed in the
block; none typed from memory, by either of us". This file holds no URL default.

THE READER (357 item 3(d)): pypdf, pure Python, optional, laptop-only, pinned by version and hash in
requirements-probe-pdf.txt (the graph engine's pattern; never requirements.txt), installed by the architect's block.
The fetched document is UNTRUSTED DATA: it is held in memory only, never written, never executed, and parsed by the
reader alone. Without the reader the report phase prints the form and stops (exit 2: the fields are not read).

NOTHING HERE WAS CONFIRMED AGAINST A LIVE ANSWER: this container reaches no nba.com host. The column headers and status
words below are HYPOTHESES (labelled on every line that uses them), printed found or not found; the body lines that
carry none of the hypothesised status words are counted and the first ROW_SAMPLE printed verbatim, so an unseen word
surfaces (law 1).

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
from urllib.parse import unquote, urljoin, urlsplit

import requests

ROOT = Path(__file__).resolve().parents[1]

OK, FAILED, REFUSED = 0, 1, 2
TAIL = "NBA-INJURY-PROBE"
# a plain, honest User-Agent (357 item 3(c)): what the client is and that it reads once; no contact detail, no browser
USER_AGENT = "sports-predictor-probe/1 (read-only research probe; one request per URL; no crawl)"
TIMEOUT = 30
READER = "pypdf"
READER_FILE = "requirements-probe-pdf.txt"
# the words an access clause is found by, case-insensitive; the probe quotes, the architect reads what they allow.
# CORE (automated access itself: every block holding one is quoted, never capped), each matched at a word's start,
# "bot"/"bots" as a whole word only ("both", "bottom" are not); BROAD (reuse and licence words, common in boilerplate:
# capped at TERMS_QUOTES on the console, every one kept in the --out receipt)
CORE_WORDS = ("automat", "robot", "scrap", "crawl", "spider", "harvest", "data mining")
BROAD_WORDS = ("extract", "reuse", "re-use", "reproduc", "redistribut", "republish", "commercial", "permission",
               "license", "licence")
CORE = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in CORE_WORDS) + r")|\bbots?\b", re.I)
BROAD = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in BROAD_WORDS) + ")", re.I)
# the page's own date line: "Last updated / modified / revised", "Effective date / as of", or a block that opens with
# "Updated:", "Revised:", "Effective:" or "Modified:"
UPDATED = re.compile(r"\blast\s+(?:updated|modified|revised)\b|\beffective\s+(?:date|as\s+of)\b"
                     r"|^\s*(?:updated|revised|effective|modified)\s*:", re.I)
TERMS_QUOTES, UPDATED_LINES, ROBOTS_LINES = 60, 5, 400
# THE WINDOW (the fourth pre-PR pass: inferring which block "governs" a clause from the markup misread real pages
# pass after pass, so the console asserts NO structure): each matched line prints with the page's own lines around
# it, in page order, verbatim: back to the nearest line ending in ":" (a heading crossed on the way is shown, never a
# stop), at most WINDOW_BACK lines, and WINDOW_AHEAD lines after. The architect reads the context; the --out receipt
# keeps the page's whole text.
WINDOW_BACK, WINDOW_AHEAD = 8, 2
# block-level tags end a block; every other tag (a, strong, em, span, b, i, time, ...) is removed in place, so a
# clause with inline markup stays whole (the pre-PR review's P1)
BLOCK_TAGS = ("p", "div", "li", "ul", "ol", "dl", "dt", "dd", "tr", "td", "th", "table", "thead", "tbody", "section",
              "article", "header", "footer", "main", "nav", "aside", "blockquote", "form", "fieldset", "br", "hr",
              "pre", "figure", "figcaption", "body", "html", "summary", "details", "legend", "caption", "address",
              "center", "dialog", "menu", "option", "tfoot", "colgroup", "dir", "button", "select", "textarea")
UPDATED_STRICT = re.compile(r"\blast\s+(?:updated|modified|revised)\b|^\s*(?:updated|revised|effective|modified)\s*:",
                            re.I)
# HYPOTHESES, never confirmed here (law 1): each is printed found / not found on the run
HEADER_WORDS = ("Game Date", "Game Time", "Matchup", "Team", "Player Name", "Current Status", "Reason")
STATUS_WORDS = ("Out", "Doubtful", "Questionable", "Probable", "Available")
REPORT_HEADER = re.compile(r"Injury\s+Report\s*:\s*(.+)", re.I)
# a stamp as a link may write it: a date YYYY-MM-DD and a clock HH[_:.-MM] AM/PM (read, never assumed: an unparsed link
# is counted and listed)
LINK_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
LINK_TIME = re.compile(r"(?<!\d)(\d{1,2})(?:[_:.\-]?(\d{2}))?\s*([AaPp][Mm])(?![A-Za-z])")
# a "Last, First" name, any script's letters (Jokić, Dončić): str patterns are Unicode
NAME_ROW = re.compile(r"\b[^\W\d_][\w'.\-]*(?: [^\W\d_][\w'.\-]*)*, [^\W\d_][\w'.\-]*")
PAGE_LINE = re.compile(r"^Page\s+\d+\s+of\s+\d+$", re.I)
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
        self.redirects: list[dict] = []           # every redirect followed: its hops are GETs of their own

    def __call__(self, url: str):
        if url in self.fetched:
            return None, {}, None, url, "REFUSED: this run already fetched this URL (nothing is fetched twice)"
        self.fetched.append(url)
        try:
            r = self.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, allow_redirects=True)
        except Exception as e:                      # noqa: BLE001 - a failed read is reported, never raised
            return None, {}, None, url, f"{type(e).__name__}: {e}"
        body = getattr(r, "content", None)
        final = getattr(r, "url", url) or url
        hops = list(getattr(r, "history", None) or [])
        if final != url or hops:
            self.redirects.append({"from": url, "to": final, "hops": len(hops)})
        err = None if r.status_code == 200 else f"HTTP {r.status_code}"
        if err is None and not body:
            err = "the answer is empty"
        return r.status_code, dict(r.headers or {}), body, final, err


def final_note(url: str, final: str) -> str:
    """The final URL when a redirect was followed, and the other host named when it left the requested one."""
    if final == url:
        return ""
    a, b = urlsplit(url).netloc, urlsplit(final).netloc
    return f" · final URL {final}" + (f" (ANOTHER HOST: {b})" if a != b else "")


def _text(body: bytes | None) -> str:
    return (body or b"").decode("utf-8", errors="replace")


def page_lines(page: str) -> list[dict]:
    """The page's visible text as LINES in page order: {"text", "heading" (True for an h1-h6)}. Comments, head,
    script, style and noscript are dropped; every block-level tag (BLOCK_TAGS), every <li> and every <br> ends a line;
    every other tag is removed in place (a clause with inline markup stays one line, as a browser shows it); a heading
    is a line of its own; entities unescaped; whitespace folded. Lines are kept WHOLE, never cut. No structure is
    inferred: a line is only the page's text between two breaks."""
    t = re.sub(r"(?s)<!--.*?-->", " ", page or "")
    t = re.sub(r"(?is)<(head|script|style|noscript)\b.*?</\1\s*>", " ", t)
    t = re.sub(r"\s+", " ", t)
    breaks = set(BLOCK_TAGS) | {"li", "br"}
    out, buf, in_h = [], [], False

    def flush(heading=False):
        text = re.sub(r"\s+", " ", html.unescape("".join(buf))).strip()
        buf.clear()
        if text:
            out.append({"text": text, "heading": heading})

    for m in re.finditer(r"<(/?)([A-Za-z][A-Za-z0-9]*)\b[^>]*>|([^<]+)|(<)", t):
        close, name, text, lt = m.group(1), (m.group(2) or "").lower(), m.group(3), m.group(4)
        if text is not None or lt:
            buf.append(text if text is not None else lt)
        elif re.fullmatch(r"h[1-6]", name):
            flush(heading=in_h)
            in_h = not close
        elif name in breaks:
            if in_h:
                buf.append(" ")                     # a break inside a heading: one heading line, words spaced
            else:
                flush()
    flush(heading=in_h)
    return out


def _window(lines: list[dict], i: int) -> tuple[int, int]:
    lo = i
    while lo > 0 and i - lo < WINDOW_BACK:
        if lo < i and lines[lo]["text"].rstrip().endswith(":"):
            break
        lo -= 1
    return lo, min(len(lines) - 1, i + WINDOW_AHEAD)


def terms_windows(page: str, cap: int | None = None) -> tuple[list[dict], list[str], int, list[dict]]:
    """(the windows, the page's own date lines, the reuse/licence windows not printed past the cap, the page's lines).
    A line (a heading included) holding a CORE word (automated access) or a BROAD word (reuse, licence) is a match;
    each match prints with
    its window (_window) of the page's own lines, verbatim and whole, overlapping windows of one kind merged. CORE
    windows first and never capped; BROAD ones after, capped at `cap` (TERMS_QUOTES when None; 0 or less: uncapped).
    Date lines: every line, headings included, matching UPDATED, the strict forms first, all kept. Nothing is
    paraphrased, cut or attributed: the window says only where the line sits on the page."""
    cap = TERMS_QUOTES if cap is None else cap
    lines = page_lines(page)
    hits = {"core": [], "broad": []}
    for i, ln in enumerate(lines):                  # a heading's own words are page text too
        kind = "core" if CORE.search(ln["text"]) else ("broad" if BROAD.search(ln["text"]) else None)
        if kind:
            hits[kind].append(i)
    windows = {"core": [], "broad": []}
    for kind in ("core", "broad"):
        for i in hits[kind]:
            lo, hi = _window(lines, i)
            w = windows[kind]
            if w and lo <= w[-1]["to"] + 1:
                w[-1]["to"] = max(w[-1]["to"], hi)
                w[-1]["matches"].append(i)
            else:
                w.append({"kind": kind, "from": lo, "to": hi, "matches": [i]})
    for kind in ("core", "broad"):
        for w in windows[kind]:
            heads = [ln["text"] for ln in lines[:w["from"]] if ln["heading"]]
            w["section"] = heads[-1] if heads else None
            w["lines"] = [{"n": n, "text": lines[n]["text"], "heading": lines[n]["heading"],
                           "match": n in w["matches"]} for n in range(w["from"], w["to"] + 1)]
    broad = windows["broad"]
    shown = broad if cap <= 0 else broad[:cap]
    strict, loose = [], []
    for ln in lines:
        s = ln["text"]
        if UPDATED.search(s) and s not in strict and s not in loose:
            (strict if UPDATED_STRICT.search(s) else loose).append(s)
    return windows["core"] + shown, strict + loose, len(broad) - len(shown), lines


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
    say(f"TERMS {a.terms_url} · HTTP {status}" + final_note(a.terms_url, final)
        + (f" · FAILED: {err}" if err else f" · {len(body)} bytes"))
    rec["terms"] = {"http": status, "final_url": final, "error": err}
    if err:
        worst = FAILED
        say("  TERMS NOT READ: the feed is not cleared (261 item 4); the report phase waits on a terms console")
    else:
        windows, updated, dropped, lines = terms_windows(_text(body))
        say("  THE PAGE'S OWN DATE LINE(S), verbatim (the strict forms first): "
            + (" | ".join(f'"{u}"' for u in updated[:UPDATED_LINES]) if updated
               else "none found (no 'last updated' / 'effective' line, in a block or a heading)")
            + (f" ... and {len(updated) - UPDATED_LINES} more date line(s), not printed (cap {UPDATED_LINES}); every "
               "one is in the --out receipt" if len(updated) > UPDATED_LINES else ""))
        if not windows:
            worst = REFUSED
            say("  NOTHING TO QUOTE: no line holds an access word " + str(list(CORE_WORDS) + ["bot(s)"])
                + " or " + str(list(BROAD_WORDS)) + "; the terms are NOT READ for this feed (the architect reads the "
                "page itself)")
        else:
            n_core = sum(1 for w in windows if w["kind"] == "core")
            say(f"  THE PAGE'S OWN TEXT AROUND EVERY ACCESS WORD, verbatim, in page order ({len(lines)} lines on the "
                f"page): {n_core} window(s) on automated access {list(CORE_WORDS) + ['bot(s)']} (every one), then "
                f"{len(windows) - n_core} on reuse and licence {list(BROAD_WORDS)}. '>' marks the matched line, '#' "
                "a heading; each window runs back to a line ending in ':' (at most "
                f"{WINDOW_BACK} lines; a heading on the way is shown) and {WINDOW_AHEAD} lines on. No structure is inferred; the architect reads what "
                "they allow, and the --out receipt holds every line of the page:")
            for w in windows:
                say(f"    --- {'automated access' if w['kind'] == 'core' else 'reuse / licence'} · page lines "
                    f"{w['from'] + 1}-{w['to'] + 1} · under {w['section']!r}")
                for ln in w["lines"]:
                    mark = "#" if ln["heading"] else (">" if ln["match"] else " ")
                    say(f"    {mark} {ln['text']}")
            if dropped:
                say(f"    ... and {dropped} more reuse/licence window(s), not printed (cap {TERMS_QUOTES}); every one is "
                    "in the --out receipt")
        rec["terms"].update(bytes=len(body), sha256=hashlib.sha256(body).hexdigest(), updated=updated,
                            windows=windows, windows_all=terms_windows(_text(body), cap=0)[0], not_printed=dropped,
                            page_lines=[("# " if ln["heading"] else "") + ln["text"] for ln in lines])
    robots = a.robots_url or robots_for(a.terms_url)
    status, hdr, body, final, err = fetch(robots)
    say(f"\nROBOTS {robots}" + ("" if a.robots_url else " (derived: --terms-url's own host)") + f" · HTTP {status}"
        + final_note(robots, final) + (f" · FAILED: {err}" if err else f" · {len(body)} bytes, as served:"))
    rec["robots"] = {"url": robots, "derived": not a.robots_url, "http": status, "final_url": final, "error": err}
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


HREF = re.compile(r"""(?<![\w-])href\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))""", re.I)


def index_links(page: str, base: str) -> list[dict]:
    """Every link to a .pdf on the index page (its href attribute alone, quoted or not; never a data-href), absolute,
    in page order, once each: its text, its file name AS WRITTEN (the path's last segment, or a .pdf name carried in
    the query) and the stamp read from that name, else from the whole URL, else from the link's text."""
    out, seen = [], set()
    for m in re.finditer(r"(?is)<a\b([^>]*)>(.*?)</a\s*>", re.sub(r"(?s)<!--.*?-->", " ", page or "")):
        h = HREF.search(m.group(1))
        if not h:
            continue
        href = html.unescape(next(g for g in h.groups() if g is not None)).strip()
        if not re.search(r"\.pdf(?:$|[?#&])", href, re.I):
            continue
        url = urljoin(base, href)
        if url in seen:
            continue
        seen.add(url)
        text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", m.group(2)))).strip()
        parts = urlsplit(url)
        name = unquote(parts.path.rsplit("/", 1)[-1])
        if not name.lower().endswith(".pdf"):
            q = re.search(r"([^/=&?]+\.pdf)", unquote(parts.query), re.I)
            name = q.group(1) if q else name
        date, clock = link_stamp(name)
        if date is None:
            date, clock = link_stamp(unquote(parts.path + "?" + parts.query))
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
    # every body line (not the document's stamp, a header row or a "Page N of M" line) holding none of the hypothesised
    # status words, whatever it holds (a team-level line, a name in any script): so an unseen word surfaces. Counted by
    # TEXT LINE, as the reader extracts them (a cell-per-line extraction splits one row over several lines).
    def is_body(ln):
        return not (REPORT_HEADER.search(ln) or PAGE_LINE.search(ln) or sum(w in ln for w in HEADER_WORDS) >= 3)
    bare = [ln for ln in lines if is_body(ln)
            and not any(re.search(rf"(?<![A-Za-z]){re.escape(w)}(?![A-Za-z])", ln) for w in STATUS_WORDS)]
    named = [ln for ln in bare if NAME_ROW.search(ln)]
    say(f"  BODY LINES WITH NONE OF THE HYPOTHESISED STATUS WORDS: {len(bare)} (of them, with a 'Last, First' name: "
        f"{len(named)}; counted by text line as extracted)"
        + (f"; the first {min(len(bare), ROW_SAMPLE)}, verbatim, so an unseen word surfaces:" if bare else ""))
    for ln in bare[:ROW_SAMPLE]:
        say(f"    | {ln[:LINE_CHARS]}")
    return {"pages": len(pages), "lines": len(lines), "stamp": stamp, "first_lines": first, "headers": headers,
            "status_lines": {w: counts.get(w, 0) for w in STATUS_WORDS}, "lines_no_status_word": len(bare),
            "name_rows_no_status_word": len(named), "lines_no_status_word_sample": bare[:ROW_SAMPLE]}


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
    say(f"INDEX {a.index_url} · HTTP {status}" + final_note(a.index_url, final)
        + (f" · FAILED: {err}" if err else f" · {len(body)} bytes"))
    rec["index"] = {"http": status, "final_url": final, "error": err}
    if err:
        return FAILED, rec
    links = index_links(_text(body), final)
    parsed = [x for x in links if x["date"]]
    say(f"  REPORT LINKS (.pdf) on the page: {len(links)} · with a date read from the link: {len(parsed)} · "
        f"unread: {len(links) - len(parsed)}")
    unread = [x for x in links if not x["date"]]
    for x in unread:
        say(f"    unread stamp: {x['file']!r} (text {x['text'][:80]!r})")
    for x in [x for x in parsed if not x["clock"]]:
        say(f"    no readable clock: {x['file']!r}")
    by_day: dict[str, list] = defaultdict(list)
    for x in parsed:
        by_day[x["date"]].append(x)
    say("  REPORTS PER DAY: each link's FILE NAME AS WRITTEN, with the clock read from it in brackets (normalized; "
        "the zone is the document's own, read below):")
    for d in sorted(by_day):
        xs = sorted(by_day[d], key=lambda x: _sort_key(d, x["clock"]))
        say(f"    {d}: {len(xs)} · {', '.join(x['clock'] or 'no clock' for x in xs)}")
        for x in xs:
            say(f"      {x['file']} ({x['clock'] or 'no readable clock'})")
    rec["links"] = {"total": len(links), "dated": len(parsed), "files": [x["file"] for x in links],
                    "unread": [x["file"] for x in unread],
                    "per_day": {d: [{"file": x["file"], "clock": x["clock"]}
                                    for x in sorted(v, key=lambda x: _sort_key(d, x["clock"]))]
                                for d, v in sorted(by_day.items())}}
    if not links:
        say("  NO REPORT LINK on the page: nothing to fetch")
        return FAILED, rec
    pick = max(parsed, key=lambda x: _sort_key(x["date"], x["clock"])) if parsed else links[0]
    why = "the newest by its link's stamp" if parsed else "the first listed (no link carries a readable stamp)"
    if parsed:
        blind = sum(1 for x in by_day[pick["date"]] if not x["clock"])
        if blind:
            why += f"; {blind} link(s) on {pick['date']} carry no readable clock, so the newest of that day is not certain"
    say(f"\nONE REPORT ({why}): {pick['url']}")
    status, hdr, data, final, err = fetch(pick["url"])
    ctype = next((v for k, v in hdr.items() if k.lower() == "content-type"), None)
    say(f"  HTTP {status}" + final_note(pick["url"], final) + f" · content-type {ctype!r}"
        + (f" · FAILED: {err}" if err else f" · {len(data)} bytes · "
        f"sha256 {hashlib.sha256(data).hexdigest()} · PDF magic {'yes' if data[:5] == b'%PDF-' else 'NO'}"))
    say("  the document is UNTRUSTED DATA: held in memory only, never written, never executed; parsed by the reader "
        "alone")
    rec["report"] = {"url": pick["url"], "file": pick["file"], "http": status, "final_url": final,
                     "content_type": ctype, "error": err}
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
    if not rec["report"]["fields"]["lines"]:
        say("  the reader extracted NO TEXT from the document (an image-only or scanned report?): its fields are NOT "
            "READ; nothing here certifies the form")
        say("\n" + MAPPING)
        return REFUSED, rec
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
    receipt = {"phase": phase, "exit": code, "fetched": fetch.fetched, "redirects": fetch.redirects, **rec}
    say(f"\nFETCHED THIS RUN ({len(fetch.fetched)}, each once): " + (" · ".join(fetch.fetched) or "nothing"))
    for r in fetch.redirects:
        say(f"  REDIRECTED: {r['from']} -> {r['to']} ({r['hops']} hop(s), each a GET of its own)")
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
