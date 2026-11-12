"""The NBA injury-report probe (scripts/nba_injury_report_probe.py; ARCHITECT 2026-11-05, addendum 261 item 1(e);
2026-11-12, addendum 357 item 3). SYNTHETIC pages and SYNTHETIC page text only: no request leaves the test (a fake GET
records every URL), no real report or terms page is held here (357 item 3(d): "no test holds a real one"), and the PDF
reader is never needed (read_pdf_pages is substituted). Every URL below is a placeholder on example.invalid."""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nba_injury_report_probe.py"
spec = importlib.util.spec_from_file_location("nba_injury_report_probe", SCRIPT)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

TERMS = "https://terms.example.invalid/terms-of-use"
INDEX = "https://reports.example.invalid/injury-report-index"

TERMS_PAGE = """<html><head><title>Terms</title><script>var robots = "ignore me";</script></head><body>
<h1>Terms of Use</h1><p>Last Updated: June 1, 2026</p>
<h2>4. Restrictions</h2><p>You may not use any robot, spider, scraper or other automated means to access the
Services. Nothing else here.</p><p>Plain sentence without the words.</p>
<h2>7. Content</h2><p>You may not reproduce or redistribute Content for commercial purposes without permission.</p>
</body></html>"""
ROBOTS = "User-agent: *\nDisallow: /private/\nAllow: /\n"
INDEX_PAGE = """<html><body><ul>
<li><a href="/files/Injury-Report_2026-11-11_01_30PM.pdf">Report 1:30 PM</a></li>
<li><a href="/files/Injury-Report_2026-11-11_05_30PM.pdf">Report 5:30 PM</a></li>
<li><a href="https://reports.example.invalid/files/Injury-Report_2026-11-12_08PM.pdf">8 PM</a></li>
<li><a href="/files/Injury-Report_2026-11-12_08PM.pdf">duplicate link</a></li>
<li><a href="/files/latest.pdf">Latest report</a></li>
<li><a href="/about.html">About</a></li>
</ul></body></html>"""
PDF = b"%PDF-1.7\nsynthetic bytes, not a real report\n%%EOF"
PAGE_TEXT = ["Injury Report: 11/12/26 08:00 PM\nPage 1 of 1\n"
             "Game Date Game Time Matchup Team Player Name Current Status Reason\n"
             "11/12/2026 07:30 (ET) AAA@BBB Synthetic Alphas Doe, John Out Injury/Illness - Left Ankle; Sprain\n"
             "Roe, Richard Questionable Rest\nPoe, Edgar Day-To-Day Synthetic\nNOT YET SUBMITTED\n"]


class Fake:
    """A GET that answers from a dict and records every URL asked."""

    def __init__(self, pages: dict):
        self.pages, self.asked = pages, []

    def __call__(self, url, headers=None, timeout=None, allow_redirects=True):
        self.asked.append((url, dict(headers or {})))
        ans = self.pages.get(url)
        if ans is None:
            return NS(status_code=404, headers={}, content=b"", url=url)
        status, body, hdr = ans
        return NS(status_code=status, headers=hdr, content=body, url=url)


def run(capsys, argv, pages):
    fake = Fake(pages)
    code = probe.main(argv, get=fake)
    out = capsys.readouterr().out
    tail = json.loads(out.strip().splitlines()[-1].split(" ", 1)[1])
    return code, out, tail, fake


def terms_pages():
    return {TERMS: (200, TERMS_PAGE.encode(), {"Content-Type": "text/html"}),
            "https://terms.example.invalid/robots.txt": (200, ROBOTS.encode(), {})}


# ---- THE TERMS PHASE (the default) ------------------------------------------------------------------------------------

def test_the_default_run_is_the_terms_phase_alone_and_fetches_no_index_and_no_report(capsys):
    """357 item 3(a): "The script's DEFAULT run is the TERMS PHASE alone [...] then it stops — no index page, no
    report." Exactly two GETs: the terms page and the host's robots.txt."""
    code, out, tail, fake = run(capsys, ["--terms-url", TERMS], terms_pages())
    assert code == probe.OK, out
    assert [u for u, _ in fake.asked] == [TERMS, "https://terms.example.invalid/robots.txt"]
    assert "TERMS PHASE ONLY (addendum 357 item 3(a)): no index page and no report was fetched" in out
    assert tail["phase"] == "terms" and tail["fetched"] == [TERMS, "https://terms.example.invalid/robots.txt"]


def test_the_access_clauses_are_quoted_verbatim_with_their_headings_and_the_pages_own_date(capsys):
    code, out, tail, _ = run(capsys, ["--terms-url", TERMS], terms_pages())
    assert 'THE PAGE\'S OWN DATE LINE(S), verbatim: "Last Updated: June 1, 2026"' in out
    assert "    [4. Restrictions]" in out and "    [7. Content]" in out
    # each clause is its WHOLE block, verbatim (the pre-PR review: never cut into sentences)
    assert ('"You may not use any robot, spider, scraper or other automated means to access the Services. Nothing else '
            'here."' in out)
    assert '"You may not reproduce or redistribute Content for commercial purposes without permission."' in out
    assert "Plain sentence without the words" not in out and "ignore me" not in out     # script text never quoted
    assert [q["heading"] for q in tail["terms"]["quoted"]] == ["4. Restrictions", "7. Content"]


def test_robots_txt_prints_as_served_and_is_derived_from_the_terms_host_unless_named(capsys):
    code, out, _, fake = run(capsys, ["--terms-url", TERMS], terms_pages())
    assert "ROBOTS https://terms.example.invalid/robots.txt (derived: --terms-url's own host)" in out
    assert "  | User-agent: *" in out and "  | Disallow: /private/" in out
    other = "https://reports.example.invalid/robots.txt"
    pages = {**terms_pages(), other: (200, b"User-agent: *\nDisallow: /\n", {})}
    code, out, tail, fake = run(capsys, ["--terms-url", TERMS, "--robots-url", other], pages)
    assert [u for u, _ in fake.asked] == [TERMS, other] and "(derived" not in out and tail["robots"]["derived"] is False


def test_no_terms_url_refuses_before_any_fetch(capsys):
    code, out, tail, fake = run(capsys, [], {})
    assert code == probe.REFUSED and fake.asked == [] and "no --terms-url" in out


def test_report_arguments_without_report_refuse_and_fetch_nothing(capsys):
    """The terms phase never takes the report phase's URLs (357 item 3(a)): refused before any fetch."""
    code, out, _, fake = run(capsys, ["--terms-url", TERMS, "--index-url", INDEX], terms_pages())
    assert code == probe.REFUSED and fake.asked == []


def test_a_page_with_no_access_clause_is_not_read_and_a_failed_fetch_is_failed(capsys):
    pages = {TERMS: (200, b"<html><body><h1>Hello</h1><p>Nothing relevant.</p></body></html>", {}),
             "https://terms.example.invalid/robots.txt": (200, ROBOTS.encode(), {})}
    code, out, _, _ = run(capsys, ["--terms-url", TERMS], pages)
    assert code == probe.REFUSED and "NOTHING TO QUOTE" in out
    code, out, _, _ = run(capsys, ["--terms-url", TERMS], {})
    assert code == probe.FAILED and "TERMS NOT READ" in out


def test_the_user_agent_is_plain_and_honest_and_every_request_carries_it(capsys):
    _, _, _, fake = run(capsys, ["--terms-url", TERMS], terms_pages())
    assert all(h.get("User-Agent") == probe.USER_AGENT for _, h in fake.asked)
    assert "Mozilla" not in probe.USER_AGENT and "probe" in probe.USER_AGENT


# ---- THE REPORT PHASE (--report, after the ruling) -------------------------------------------------------------------

def report_pages():
    return {INDEX: (200, INDEX_PAGE.encode(), {"Content-Type": "text/html"}),
            "https://reports.example.invalid/files/Injury-Report_2026-11-12_08PM.pdf":
                (200, PDF, {"Content-Type": "application/pdf"})}


def test_the_report_phase_is_refused_without_its_ruling_or_its_index(capsys):
    code, out, _, fake = run(capsys, ["--report", "--index-url", INDEX], report_pages())
    assert code == probe.REFUSED and fake.asked == [] and "--terms-ruling" in out
    code, out, _, fake = run(capsys, ["--report", "--terms-ruling", "addendum 999 item 1"], report_pages())
    assert code == probe.REFUSED and fake.asked == [] and "--index-url" in out


def test_one_index_read_and_one_document_the_newest_by_its_links_stamp(capsys, monkeypatch):
    """357 item 3(c): one index read and one document; no crawl, nothing fetched twice. The duplicate link and the
    non-PDF link are not reports; the undated link is counted and listed; the reports per day print as written."""
    monkeypatch.setattr(probe, "read_pdf_pages", lambda data: PAGE_TEXT)
    code, out, tail, fake = run(capsys, ["--report", "--index-url", INDEX, "--terms-ruling", "addendum 999 item 1"],
                                report_pages())
    assert code == probe.OK, out
    assert [u for u, _ in fake.asked] == [INDEX, "https://reports.example.invalid/files/Injury-Report_2026-11-12_08PM.pdf"]
    assert "REPORT LINKS (.pdf) on the page: 4 · with a date read from the link: 3 · unread: 1" in out
    assert "unread stamp: 'latest.pdf'" in out
    assert "    2026-11-11: 2 · 01:30 PM, 05:30 PM" in out and "    2026-11-12: 1 · 08:00 PM" in out
    assert "ONE REPORT (the newest by its link's stamp)" in out
    assert "PDF magic yes" in out and "UNTRUSTED DATA" in out
    assert tail["report"]["file"] == "Injury-Report_2026-11-12_08PM.pdf" and tail["report"]["reader"] == "pypdf"


def test_the_fields_print_as_written_with_the_hypotheses_labelled_and_unseen_words_surfaced(capsys, monkeypatch):
    monkeypatch.setattr(probe, "read_pdf_pages", lambda data: PAGE_TEXT)
    code, out, tail, _ = run(capsys, ["--report", "--index-url", INDEX, "--terms-ruling", "addendum 999 item 1"],
                             report_pages())
    assert 'THE DOCUMENT\'S OWN STAMP (hypothesis: a line \'Injury Report: ...\'): "Injury Report: 11/12/26 08:00 PM"' \
        in out
    assert "COLUMN HEADERS (HYPOTHESES" in out and "Player Name: found" in out
    assert "STATUS WORDS (HYPOTHESES" in out and "Out: 1" in out and "Questionable: 1" in out and "Probable: 0" in out
    assert "| Poe, Edgar Day-To-Day Synthetic" in out          # a status word no hypothesis names, printed verbatim
    f = tail["report"]["fields"]
    assert f["status_lines"]["Out"] == 1 and f["lines_no_status_word"] == 2 and f["name_rows_no_status_word"] == 1
    assert "| NOT YET SUBMITTED" in out                          # a team-level line surfaces too
    assert "THE MAPPING, printed and NOT built" in out and "`injury_status`" in out


def test_without_the_reader_the_form_prints_and_the_fields_are_not_read(capsys, monkeypatch):
    def absent(data):
        raise ImportError("No module named 'pypdf'")
    monkeypatch.setattr(probe, "read_pdf_pages", absent)
    code, out, tail, _ = run(capsys, ["--report", "--index-url", INDEX, "--terms-ruling", "addendum 999 item 1"],
                             report_pages())
    assert code == probe.REFUSED
    assert "content-type 'application/pdf'" in out and "READER NOT INSTALLED (pypdf, requirements-probe-pdf.txt" in out
    assert tail["report"]["reader"] is None and tail["report"]["bytes"] == len(PDF)


def test_nothing_is_fetched_twice_in_a_run():
    fake = Fake({TERMS: (200, b"x", {})})
    f = probe.Fetcher(fake)
    f(TERMS)
    status, _, _, _, err = f(TERMS)
    assert status is None and "nothing is fetched twice" in err and len(fake.asked) == 1


# ---- the file: no URL typed, nothing written, the reader optional ---------------------------------------------------

def test_the_script_holds_no_url_and_writes_nothing_but_its_receipt():
    """357 item 3(b): "none typed from memory, by either of us"; 357 item 3(d): "The fetched document is kept
    nowhere". No http(s) literal in the code (the docstring names none either); no write call but --out's receipt."""
    src = SCRIPT.read_text()
    tree = ast.parse(src)
    literals = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert not [s for s in literals if "http://" in s or "https://" in s]
    assert src.count("write_text(") == 1 and "write_bytes(" not in src and "open(" not in src.replace("urlopen(", "")


def test_the_reader_is_optional_pinned_by_hash_and_never_in_requirements_txt():
    req = (ROOT / "requirements-probe-pdf.txt").read_text()
    pins = [ln for ln in req.splitlines() if ln and not ln.startswith("#")]
    assert pins == ["pypdf==6.21.4 --hash=sha256:33e4fb41ca352810eb4e9838aa0d82d6888a5f8bf682f43e99cce5faa666255c"]
    assert "pypdf" not in (ROOT / "requirements.txt").read_text()
    tree = ast.parse(SCRIPT.read_text())
    top = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert not [n for n in top if "pypdf" in ast.dump(n)]        # imported inside read_pdf_pages only


def test_a_receipt_under_data_is_refused(tmp_path, capsys):
    assert probe.main(["--terms-url", TERMS, "--out", str(tmp_path / "data" / "r.json")], get=Fake({})) == probe.REFUSED
    assert "law 5" in capsys.readouterr().out


# ---- the pre-PR adversarial review's findings (each reproduced on 0863278f, fail-first) -----------------------------

INLINE_PAGE = """<html><body><!-- <p>Old text: no robots at all, and Last Updated: 1999.</p> -->
<p><strong>Last Updated:</strong> October 1, 2025</p>
<h2>Prohibited <span>Uses</span></h2>
<p>You may <strong>not</strong> use any <a href="/x">robot</a>, spider or other automated means (e.g. scripts) to
access the Services; nor may you do so through U.S. intermediaries.</p>
<p>You agree that you will not:</p><ul><li>scrape, harvest or extract data from the Services;</li>
<li>frame the Services.</li></ul>
<p>Both parties agree. The bottom line is simple.</p>
</body></html>"""


def test_review_inline_markup_keeps_the_clause_whole_with_its_negation_and_the_date_with_its_label():
    """P1 (three lenses): every tag was a block break, so "You may <strong>not</strong> use any <a>robot</a>" was cut
    into fragments and the negation never printed; "<strong>Last Updated:</strong> October 1, 2025" lost its date.
    A clause is now its whole block (paragraph or list item), inline tags kept in place; comments never read."""
    quoted, updated, dropped = probe.terms_quotes(INLINE_PAGE)
    texts = [q["text"] for q in quoted]
    assert ("You may not use any robot, spider or other automated means (e.g. scripts) to access the Services; nor "
            "may you do so through U.S. intermediaries.") in texts
    assert updated == ["Last Updated: October 1, 2025"]                      # the comment's 1999 line is not read
    assert not [t for t in texts if "1999" in t or "Old text" in t]
    assert [q["heading"] for q in quoted if q["text"].startswith("You may not")] == ["Prohibited Uses"]


def test_review_a_list_item_prints_with_its_lead_in():
    quoted, _, _ = probe.terms_quotes(INLINE_PAGE)
    li = [q for q in quoted if q["text"].startswith("scrape, harvest")]
    assert li and li[0]["lead_in"] == "You agree that you will not:"


def test_review_bot_is_a_whole_word_and_the_core_access_words_are_never_capped(monkeypatch):
    """P2: 'bot' matched 'Both'/'bottom', and the 60-quote cap filled in page order with broad words ('license',
    'permission') before the robots clause. Core words are quoted in full; only the broad ones are capped."""
    quoted, _, _ = probe.terms_quotes(INLINE_PAGE)
    assert not [q for q in quoted if q["text"].startswith("Both parties")]
    filler = "".join(f"<p>Clause {i}: the license and permission terms apply.</p>" for i in range(80))
    page = filler + "<h2>Access</h2><p>No robots may access the Services.</p>"
    monkeypatch.setattr(probe, "TERMS_QUOTES", 10)
    quoted, _, dropped = probe.terms_quotes(page)
    assert "No robots may access the Services." in [q["text"] for q in quoted]          # core: never capped
    assert len([q for q in quoted if q["kind"] == "broad"]) == 10 and dropped == 70
    assert quoted[0]["kind"] == "core"                                                 # core printed first


@pytest.mark.parametrize("line", ["Updated: March 3, 2026", "Revised: 2026-03-03", "Effective: March 3, 2026",
                                  "Last modified 03/03/2026", "Effective as of March 3, 2026"])
def test_review_the_date_line_forms(line):
    _, updated, _ = probe.terms_quotes(f"<p>{line}</p><p>No robots.</p>")
    assert updated == [line]


def test_review_redirects_print_their_final_url_and_every_hop(capsys):
    """P2: requests follows redirects; the robots and report lines never printed the final URL, and the hops (their
    own GETs) were not listed in FETCHED THIS RUN."""
    class Redirecting(Fake):
        def __call__(self, url, headers=None, timeout=None, allow_redirects=True):
            r = super().__call__(url, headers, timeout, allow_redirects)
            if url.endswith("robots.txt"):
                r.url = "https://other.example.invalid/robots.txt"
                r.history = [NS(url=url, status_code=301)]
            return r
    fake = Redirecting(terms_pages())
    code = probe.main(["--terms-url", TERMS], get=fake)
    out = capsys.readouterr().out
    tail = json.loads(out.strip().splitlines()[-1].split(" ", 1)[1])
    assert "final URL https://other.example.invalid/robots.txt (ANOTHER HOST: other.example.invalid)" in out
    assert tail["robots"]["final_url"] == "https://other.example.invalid/robots.txt"
    assert tail["redirects"] == [{"from": "https://terms.example.invalid/robots.txt",
                                  "to": "https://other.example.invalid/robots.txt", "hops": 1}]


def test_review_every_dated_link_prints_its_file_name_as_written_and_unquoted_or_query_links_are_read(capsys,
                                                                                                   monkeypatch):
    """P1/P2: the per-day line printed normalized clocks under "AS WRITTEN" and no dated file name; an unquoted href was
    dropped silently and a data-href was taken for the link; a stamp in the query string was never read."""
    page = ('<a data-href="/x/nope.pdf" href="/files/Injury-Report_2026-11-12_05PM.pdf">a</a>'
            '<a href=/files/Injury-Report_2026-11-12_01_30PM.pdf>b</a>'
            '<a href="/download?file=Injury-Report_2026-11-11_08PM.pdf">c</a>')
    pages = {INDEX: (200, page.encode(), {}),
             "https://reports.example.invalid/files/Injury-Report_2026-11-12_05PM.pdf": (200, PDF, {})}
    monkeypatch.setattr(probe, "read_pdf_pages", lambda data: PAGE_TEXT)
    code, out, tail, fake = run(capsys, ["--report", "--index-url", INDEX, "--terms-ruling", "addendum 999 item 1"],
                                pages)
    assert "REPORT LINKS (.pdf) on the page: 3 · with a date read from the link: 3 · unread: 0" in out
    assert "      Injury-Report_2026-11-12_01_30PM.pdf (01:30 PM)" in out
    assert "      Injury-Report_2026-11-12_05PM.pdf (05:00 PM)" in out
    assert "      Injury-Report_2026-11-11_08PM.pdf (08:00 PM)" in out
    assert "nope.pdf" not in out
    assert "ONE REPORT (the newest by its link's stamp): https://reports.example.invalid/files/Injury-Report_2026-11-12_05PM.pdf" in out
    assert sorted(tail["links"]["files"]) == sorted(["Injury-Report_2026-11-12_05PM.pdf",
                                                     "Injury-Report_2026-11-12_01_30PM.pdf",
                                                     "Injury-Report_2026-11-11_08PM.pdf"])


def test_review_a_newest_date_link_with_no_readable_clock_makes_the_pick_say_so(capsys, monkeypatch):
    page = ('<a href="/f/Injury-Report_2026-11-12_05PM.pdf">a</a><a href="/f/Injury-Report_2026-11-12_late.pdf">b</a>')
    pages = {INDEX: (200, page.encode(), {}),
             "https://reports.example.invalid/f/Injury-Report_2026-11-12_05PM.pdf": (200, PDF, {})}
    monkeypatch.setattr(probe, "read_pdf_pages", lambda data: PAGE_TEXT)
    code, out, _, _ = run(capsys, ["--report", "--index-url", INDEX, "--terms-ruling", "addendum 999 item 1"], pages)
    assert "no readable clock: 'Injury-Report_2026-11-12_late.pdf'" in out
    assert "the newest by its link's stamp; 1 link(s) on 2026-11-12 carry no readable clock" in out


def test_review_unseen_status_words_surface_on_any_line_and_names_with_diacritics_read(capsys, monkeypatch):
    """P2: only ASCII 'Last, First' lines surfaced; a team-level line ('NOT YET SUBMITTED') or a name with a
    diacritic never did, so an unseen status word there was never printed."""
    text = ["Injury Report: 11/12/26 08:00 PM\nGame Date Game Time Matchup Team Player Name Current Status Reason\n"
            "Jokić, Nikola Out Injury\nDončić, Luka Suspended League\nSynthetic Alphas NOT YET SUBMITTED\n"]
    monkeypatch.setattr(probe, "read_pdf_pages", lambda data: text)
    code, out, tail, _ = run(capsys, ["--report", "--index-url", INDEX, "--terms-ruling", "addendum 999 item 1"],
                             report_pages())
    assert "| Dončić, Luka Suspended League" in out and "| Synthetic Alphas NOT YET SUBMITTED" in out
    f = tail["report"]["fields"]
    assert f["lines_no_status_word"] == 2 and f["name_rows_no_status_word"] == 1
