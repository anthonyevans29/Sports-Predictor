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


def test_the_access_lines_print_verbatim_in_their_windows_with_the_pages_own_date(capsys):
    code, out, tail, _ = run(capsys, ["--terms-url", TERMS], terms_pages())
    assert ('THE PAGE\'S OWN DATE LINE(S), verbatim (the strict forms first), each with the line after it: '
            '"Last Updated: June 1, 2026" (the line after it: "4. Restrictions")') in out
    assert "    # 4. Restrictions" in out and "    # 7. Content" in out
    assert ("    > You may not use any robot, spider, scraper or other automated means to access the Services. Nothing "
            "else here.") in out
    assert "    > You may not reproduce or redistribute Content for commercial purposes without permission." in out
    assert "ignore me" not in out                                   # script text is never page text
    assert tail["terms"]["page_lines"][0] == {"line": 1, "heading": True, "text": "Terms of Use"}   # every line kept
    assert [w["kind"] for w in tail["terms"]["windows"]] == ["core", "broad"]


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

def win(page):
    """The windows' text as the console prints them, joined (one window per block, '---' between)."""
    windows, updated, dropped, lines = probe.terms_windows(page)
    return "\n---\n".join("\n".join(("#" if ln["heading"] else (">" if ln["match"] else " ")) + " " + ln["text"]
                                     for ln in w["lines"]) for w in windows)


def ordered(hay, *needles):
    pos = 0
    for n in needles:
        i = hay.find(n, pos)
        assert i >= 0, (n, hay)
        pos = i + len(n)


# ---- every case the four pre-PR adversarial passes raised, on the window design (each reproduced, fail-first on the
# earlier designs): the console prints the page's own lines around every access word, verbatim, in page order, and
# asserts no structure; the receipt holds every line of the page

INLINE_PAGE = """<html><body><!-- <p>Old text: no robots at all, and Last Updated: 1999.</p> -->
<p><strong>Last Updated:</strong> October 1, 2025</p>
<h2>Prohibited <span>Uses</span></h2>
<p>You may <strong>not</strong> use any <a href="/x">robot</a>, spider or other automated means (e.g. scripts) to
access the Services; nor may you do so through U.S. intermediaries.</p>
<p>You agree that you will not:</p><ul><li>scrape, harvest or extract data from the Services;</li>
<li>frame the Services.</li></ul>
<p>Both parties agree. The bottom line is simple.</p>
</body></html>"""


def test_pass1_inline_markup_keeps_a_line_whole_with_its_negation_and_the_date_with_its_label():
    w = win(INLINE_PAGE)
    assert ("> You may not use any robot, spider or other automated means (e.g. scripts) to access the Services; nor "
            "may you do so through U.S. intermediaries.") in w
    _, updated, _, lines = probe.terms_windows(INLINE_PAGE)
    assert updated == ["Last Updated: October 1, 2025"]
    assert not [ln for ln in lines if "1999" in ln["text"] or "Old text" in ln["text"]]   # comments never read
    assert "# Prohibited Uses" in w


def test_pass1_a_list_item_prints_after_its_lead_in_and_both_is_not_bot():
    ordered(win(INLINE_PAGE), "  You agree that you will not:", "> scrape, harvest or extract data from the Services;")
    assert "> Both parties agree" not in win(INLINE_PAGE)


def test_pass1_the_automated_access_windows_are_never_capped_and_come_first(monkeypatch):
    filler = "".join(f"<p>Section {i}:</p><p>The license applies {i}.</p><p>a.</p><p>b.</p><p>c.</p><p>d.</p>"
                     for i in range(30))                                     # each its own window: a ':' line opens it
    page = filler + "<h2>Access</h2><p>No robots may access the Services.</p>"
    monkeypatch.setattr(probe, "TERMS_QUOTES", 10)
    windows, _, dropped, _ = probe.terms_windows(page)
    assert windows[0]["kind"] == "core" and "No robots may access the Services." in [
        ln["text"] for ln in windows[0]["lines"]]
    assert len([w for w in windows if w["kind"] == "broad"]) == 10 and dropped == 20
    assert len(probe.terms_windows(page, cap=0)[0]) == 31                       # the receipt's list: every window


@pytest.mark.parametrize("line", ["Updated: March 3, 2026", "Revised: 2026-03-03", "Effective: March 3, 2026",
                                  "Last modified 03/03/2026", "Effective as of March 3, 2026"])
def test_pass1_the_date_line_forms(line):
    assert probe.terms_windows(f"<p>{line}</p><p>No robots.</p>")[1] == [line]


def test_pass2_a_window_shows_a_heading_crossed_and_a_nested_items_parent_words():
    w = win('<h2>Prohibited</h2><p>You may not do any of the following:</p><ul><li>sell content</li></ul>'
            '<h2>Search engines</h2><ul><li>Crawlers of licensed search engines are permitted.</li></ul>')
    ordered(w, "You may not do any of the following:", "# Search engines",
            "> Crawlers of licensed search engines are permitted.")             # the section boundary is visible
    ordered(win('<p>You agree that you will:</p><ul><li>comply with law;</li><li>not, without permission:<ul><li>use '
                'any robot or scraper</li></ul></li></ul>'), "  not, without permission:", "> use any robot or scraper")


@pytest.mark.parametrize("item", ["<li><p>use any robot or spider</p></li>", "<li><div>use any robot or spider</div></li>",
                                  "<li>(a) sell;<br>use any robot or spider</li>"])
def test_pass2_an_items_inner_block_prints_after_the_lead_in(item):
    ordered(win(f"<p>You agree not to:</p><ul>{item}</ul>"), "  You agree not to:", "> use any robot or spider")


def test_pass2_block_rendered_tags_break_lines_and_a_br_in_a_heading_is_a_space():
    w = win("<details><summary>Automated access</summary>No robots may access the site.</details>")
    ordered(w, "> Automated access", "> No robots may access the site.")
    assert "# Section 9 Automated Access" in win("<h2>Section 9<br/>Automated Access</h2><p>No scraping.</p>")


def test_pass2_a_date_line_as_a_heading_is_found_and_strict_forms_come_first(capsys):
    assert probe.terms_windows("<h1>Terms of Use</h1><h4>Last Updated: October 1, 2026</h4><p>No robots.</p>")[1] == [
        "Last Updated: October 1, 2026"]
    page = "".join(f"<p>Changes become binding on the effective date stated in notice {i}.</p>" for i in range(6))
    page += "<p>No robots.</p><p>Last updated: Nov 1, 2026</p>"
    updated = probe.terms_windows(page)[1]
    assert updated[0] == "Last updated: Nov 1, 2026" and len(updated) == 7
    pages = {TERMS: (200, page.encode(), {}), "https://terms.example.invalid/robots.txt": (200, ROBOTS.encode(), {})}
    _, out, _, _ = run(capsys, ["--terms-url", TERMS], pages)
    assert '"Last updated: Nov 1, 2026"' in out and "and 2 more date line(s), not printed" in out


def test_pass2_text_in_a_heading_never_closed_is_kept():
    assert "No robots may access the site." in win("<h2>Terms<h2>No robots may access the site. <p>Robots again.")


def test_pass3_items_without_close_tags_print_in_page_order_with_the_paragraph_after():
    ordered(win("<h2>Use</h2><p>You may:</p><ul><li>browse the site<li>use a robot to read the injury report PDF</ul>"
                "<p>You may not scrape the Site.</p>"),
            "  You may:", "  browse the site", "> use a robot to read the injury report PDF",
            "> You may not scrape the Site.")


def test_pass3_a_br_keeps_the_negation_above_its_lines():
    ordered(win("<h2>Restrictions</h2><p>You may not:<br>- use any robot, spider or scraper<br>- reproduce the content</p>"),
            "  You may not:", "> - use any robot, spider or scraper", "- reproduce the content")
    ordered(win("<p>Permitted uses:</p><ul><li><p>Prohibited. You will not:</p><p>use any robot or scraper</p></li></ul>"),
            "  Prohibited. You will not:", "> use any robot or scraper")


def test_pass4_a_proviso_after_a_nested_list_prints_in_the_window():
    ordered(win("<h2>Access</h2><ul><li>You may access the Services with automated tools: <ul><li>RSS readers</li>"
                "<li>robots that honour robots.txt</li></ul> only after NBA issues you a written API key.</li></ul>"),
            "> You may access the Services with automated tools:", "> robots that honour robots.txt",
            "only after NBA issues you a written API key.")


def test_pass4_a_long_line_prints_whole_with_its_access_word():
    page = "<ol><li><h2>4. Use</h2><p>" + ("General conduct text. " * 90) + "</p><p>You may not scrape the site.</p></li></ol>"
    assert "> You may not scrape the site." in win(page)
    long = "<p>" + ("ALL CAPS TERMS TEXT. " * 90) + "YOU MAY NOT USE ANY ROBOT.</p>"
    assert win(long).endswith("YOU MAY NOT USE ANY ROBOT.")                    # never cut


def test_pass4_a_repeated_item_prints_under_each_of_its_lead_ins():
    ordered(win("<h2>Access</h2><p>Licensed partners may:</p><ul><li>use automated tools to access feeds</li></ul>"
                "<p>Other users may not:</p><ul><li>use automated tools to access feeds</li></ul>"),
            "Licensed partners may:", "> use automated tools to access feeds", "Other users may not:",
            "> use automated tools to access feeds")


def test_pass4_a_heading_inside_an_item_does_not_hide_the_lead_in():
    ordered(win("<h2>Use</h2><p>You may not:</p><ul><li><h3>Automated</h3>use robots</li></ul>"),
            "  You may not:", "# Automated", "> use robots")


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


def test_r2_a_report_whose_text_does_not_extract_says_so_and_certifies_nothing(capsys, monkeypatch):
    monkeypatch.setattr(probe, "read_pdf_pages", lambda data: [""])
    code, out, tail, _ = run(capsys, ["--report", "--index-url", INDEX, "--terms-ruling", "addendum 999 item 1"],
                             report_pages())
    assert code == probe.REFUSED
    assert "the reader extracted NO TEXT" in out and tail["report"]["fields"]["lines"] == 0


# ---- the fifth adversarial pass (on 6e43355b, the window design; each reproduced there, fail-first) -----------------

@pytest.mark.parametrize("text", ["engage in data-mining of NBA content", "engage in datamining of NBA content",
                                  "engage in data‑mining of NBA content", "text-and-data-mining is prohibited",
                                  "no webcrawlers", "no screenscraping", "no chatbots"])
def test_r5_the_automated_access_words_read_their_compounds_and_hyphen_forms(text):
    windows = probe.terms_windows(f"<p>{text}.</p>")[0]
    assert windows and windows[0]["kind"] == "core", text


@pytest.mark.parametrize("text", ["Both parties agree.", "The bottom line.", "We may update these terms."])
def test_r5_the_widened_words_still_skip_plain_words(text):
    assert not [w for w in probe.terms_windows(f"<p>{text}</p>")[0] if w["kind"] == "core"]


def test_r5_the_window_header_claims_no_section_and_names_the_nearest_heading_above_the_match(capsys):
    page = ("<h2>1. License</h2>" + "".join(f"<p>para {i}.</p>" for i in range(9))
            + "<h2>2. Prohibited Conduct</h2><p>You agree that you will not access the Services through bots.</p>")
    pages = {TERMS: (200, page.encode(), {}), "https://terms.example.invalid/robots.txt": (200, ROBOTS.encode(), {})}
    _, out, tail, _ = run(capsys, ["--terms-url", TERMS], pages)
    assert "under '1. License'" not in out and "under " not in out.split("ROBOTS")[0].split("THE PAGE'S OWN TEXT")[1]
    assert "the nearest heading at or above line 12: '2. Prohibited Conduct'" in out
    w = tail["terms"]["windows"][0]
    assert "section" not in w and w["heading_above_first_match"] == "2. Prohibited Conduct"
    assert w["matches"] == [12] and tail["terms"]["page_lines"][11] == {"line": 12, "heading": False,
                                                                         "text": "You agree that you will not access the Services through bots."}


def test_r5_a_matched_heading_is_marked_as_both():
    w = probe.terms_windows("<h2>Robots and Spiders</h2><p>See the policy.</p>")[0][0]
    assert w["lines"][0]["heading"] and w["lines"][0]["match"]
    assert "#> Robots and Spiders" in probe.console_window_lines(w)


@pytest.mark.parametrize("page", ['<p>You may not <a href="/x" onclick="a=>b">use robots</a> on the Site.</p>',
                                  "<p data-x='1>0'>You may not use robots on the Site.</p>"])
def test_r5_a_greater_than_inside_a_quoted_attribute_is_not_page_text(page):
    texts = [ln["text"] for ln in probe.page_lines(page)]
    assert texts == ["You may not use robots on the Site."]


@pytest.mark.parametrize("line", ["Date of Last Revision: May 1, 2025", "Last Revision: 2025", "Revised on May 1, 2025",
                                  "Updated November 1, 2025", "Updated on: 5/1/2025"])
def test_r5_more_date_line_forms(line):
    assert probe.terms_windows(f"<p>{line}</p><p>No robots.</p>")[1] == [line]


def test_r5_a_date_in_its_own_block_prints_with_its_label(capsys):
    page = "<div>Last updated:</div><div>May 1, 2025</div><p>No robots.</p>"
    pages = {TERMS: (200, page.encode(), {}), "https://terms.example.invalid/robots.txt": (200, ROBOTS.encode(), {})}
    _, out, tail, _ = run(capsys, ["--terms-url", TERMS], pages)
    assert '"Last updated:" (the line after it: "May 1, 2025")' in out
    assert tail["terms"]["updated"] == [{"line": "Last updated:", "next": "May 1, 2025"}]


def test_r5_comments_doctype_and_xml_declarations_add_nothing():
    page = ("<!DOCTYPE html><?xml version='1.0'?><p>Last updated <!-- -->10<!-- -->/<!-- -->1<!-- -->/<!-- -->2025"
            "</p>")
    assert [ln["text"] for ln in probe.page_lines(page)] == ["Last updated 10/1/2025"]


# ---- the sixth adversarial pass (on d120d7c6; each reproduced there, fail-first): the page is now parsed by the
# standard library's html.parser, which reads script/style contents, comments, declarations and attribute quoting
# by the HTML rules, not by a hand-written regex

def test_r6_a_comment_opener_inside_a_script_drops_no_page_text():
    page = ("<h2>1. Access</h2><p>You may not use any robot or spider to access the Site.</p>"
            "<script>function strip(h){return h.split('<!--')[0]}</script><h2>2. Data</h2>"
            "<p>You may not scrape, crawl or data-mine the Site.</p><p>No bots.</p><!-- /main -->"
            "<footer><p>Last updated: January 1, 2026</p></footer>")
    texts = [ln["text"] for ln in probe.page_lines(page)]
    assert texts == ["1. Access", "You may not use any robot or spider to access the Site.", "2. Data",
                     "You may not scrape, crawl or data-mine the Site.", "No bots.", "Last updated: January 1, 2026"]


@pytest.mark.parametrize("link", ["<a href='/help' title='NBA's Help Center'>Help Center</a>",
                                  "<a href=/fan's-guide>Help Center</a>", '<a href="/privacy"">Help Center</a>'])
def test_r6_a_stray_quote_in_a_tag_never_swallows_the_page(link):
    page = (f"<p>Questions? See the {link}.</p><h2>Prohibited Conduct</h2>"
            "<p>You may not use any robot, spider, scraper or other automated means to access the Services.</p>")
    texts = [ln["text"] for ln in probe.page_lines(page)]
    assert texts == ["Questions? See the Help Center.", "Prohibited Conduct",
                     "You may not use any robot, spider, scraper or other automated means to access the Services."]


def test_r6_a_date_line_is_paired_with_its_own_next_line():
    page = ("<p>Last Updated: October 1, 2025</p><p>Intro</p><p>No robots.</p><h3>Last Updated</h3>"
            "<p>November 3, 2026</p>")
    d = probe.date_lines(probe.page_lines(page))
    assert {"line": "Last Updated", "next": "November 3, 2026"} in d
    assert {"line": "Last Updated: October 1, 2025", "next": "Intro"} in d


def test_r6_soft_hyphens_and_zero_width_characters_the_browser_hides_are_dropped():
    page = "<p>No auto­mated access and no data​-mining.</p>"
    assert probe.page_lines(page)[0]["text"] == "No automated access and no data-mining."
    assert probe.terms_windows(page)[0][0]["kind"] == "core"


def test_r6_the_header_says_at_or_above_when_the_match_is_the_heading(capsys):
    page = "<h2>Robots</h2><p>See the policy.</p>"
    pages = {TERMS: (200, page.encode(), {}), "https://terms.example.invalid/robots.txt": (200, ROBOTS.encode(), {})}
    _, out, _, _ = run(capsys, ["--terms-url", TERMS], pages)
    assert "the nearest heading at or above line 1: 'Robots'" in out


# ---- the seventh adversarial pass (on 41d52c8c; each reproduced there, fail-first) -----------------------------------

@pytest.mark.parametrize("page", [
    "<!doctype html><html><head><meta charset=utf-8><title>Terms</title><body><h2>Use</h2>"
    "<p>You may not use robots or scrapers.</p></body></html>",
    "<html><head><link rel=stylesheet href=x.css>\n<body><p>You may not use robots or scrapers.</p>",
    "<html><body><p>A</p><head><p>You may not use robots or scrapers.</p></body></html>",
    "<p>A</p><svg><title>icon</svg><p>You may not use robots or scrapers.</p>"])
def test_r7_an_omitted_head_close_or_a_stray_head_or_title_never_drops_the_page(page):
    """P1: 'head' was a skip ended only by </head>, which HTML lets a page omit: the whole page parsed to nothing and
    the console said NOTHING TO QUOTE on a page that forbids robots."""
    assert "You may not use robots or scrapers." in [ln["text"] for ln in probe.page_lines(page)]
    assert "Terms" not in [ln["text"] for ln in probe.page_lines(page)]               # the head's <title> is not text


def test_r7_a_heading_the_browser_closes_does_not_swallow_the_blocks_after_it():
    lines = probe.page_lines("<section><h2>7. Automated access</section><section><p>You may not use robots or "
                             "scrapers.</p><p>Last updated: Oct 1, 2026</p></section>")
    assert [(ln["text"], ln["heading"]) for ln in lines] == [("7. Automated access", True),
                                                             ("You may not use robots or scrapers.", False),
                                                             ("Last updated: Oct 1, 2026", False)]
    lines = probe.page_lines("<h2>7. Prohibited Uses<h2><p>You may not:</p><ul><li>use bots;</li><li>copy content."
                             "</li></ul><p>Other text.</p>")
    assert [ln["text"] for ln in lines] == ["7. Prohibited Uses", "You may not:", "use bots;", "copy content.",
                                            "Other text."]


def test_r7_a_page_that_parses_to_no_line_says_so_never_nothing_to_quote(capsys, monkeypatch):
    monkeypatch.setattr(probe, "page_lines", lambda page: [])
    _, out, tail, _ = run(capsys, ["--terms-url", TERMS], terms_pages())
    assert "the page parsed to 0 lines: NOT READ" in out and "NOTHING TO QUOTE" not in out
    assert tail["exit"] == probe.FAILED
