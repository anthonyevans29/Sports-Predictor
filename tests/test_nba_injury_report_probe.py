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
        self.pages, self.asked, self.follow_flags = pages, [], []

    def __call__(self, url, headers=None, timeout=None, allow_redirects=True):
        self.asked.append((url, dict(headers or {})))
        self.follow_flags.append(allow_redirects)
        ans = self.pages.get(url)
        if ans is None:
            return NS(status_code=404, headers={}, content=b"", url=url)
        status, body, hdr = ans
        if 300 <= status < 400 and allow_redirects:         # what requests does: the target is a GET of its own
            return self(hdr["Location"], headers, timeout, allow_redirects)
        return NS(status_code=status, headers=hdr, content=body, url=url)


def run(capsys, argv, pages):
    """(exit, console, the --out RECEIPT, the fake GET). The tail line is a summary; the evidence is the receipt."""
    import tempfile
    fake = Fake(pages)
    receipt = Path(tempfile.mkdtemp()) / "receipt.json"
    if "--out" not in argv:
        argv = [*argv, "--out", str(receipt)]
    code = probe.main(argv, get=fake)
    out = capsys.readouterr().out
    rec = json.loads(receipt.read_text()) if receipt.exists() else json.loads(out.strip().splitlines()[-1].split(" ", 1)[1])
    return code, out, rec, fake


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
    status, _, _, err = f(TERMS)
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


# ---- the eighth pass (on ccd70940), the one P1 under addendum 360 item 2(b): a line dropped from the RECEIPT -----------

def test_r8_every_robots_line_is_in_the_receipt_past_the_console_cap(capsys, tmp_path):
    robots = "User-agent: *\n" + "".join(f"Allow: /p{i}\n" for i in range(420)) + "User-agent: *\nDisallow: /injury-report/\n"
    pages = {**terms_pages(), "https://terms.example.invalid/robots.txt": (200, robots.encode(), {})}
    out_file = tmp_path / "r.json"
    code = probe.main(["--terms-url", TERMS, "--out", str(out_file)], get=Fake(pages))
    out = capsys.readouterr().out
    assert "not printed (cap 400); every line is in the --out receipt" in out
    rec = json.loads(out_file.read_text())
    lines = rec["robots"]["text_lines"]
    assert len(lines) == 423 and lines[-1] == {"line": 423, "text": "Disallow: /injury-report/"}


# ---- Codex's round on #970 (each fail-first) --------------------------------------------------------------------------

def test_codex_the_tail_line_is_a_summary_never_the_whole_receipt(capsys, tmp_path):
    out_file = tmp_path / "r.json"
    probe.main(["--terms-url", TERMS, "--out", str(out_file)], get=Fake(terms_pages()))
    last = capsys.readouterr().out.strip().splitlines()[-1]
    tail = json.loads(last.split(" ", 1)[1])
    assert "terms" not in tail and "robots" not in tail and '"text"' not in last and "You may not" not in last
    assert tail["phase"] == "terms" and tail["exit"] == probe.OK and tail["receipt"] == str(out_file)
    assert tail["page_lines"] == 7 and tail["robots_lines"] == 3
    full = json.loads(out_file.read_text())                         # the evidence stays in the receipt
    assert len(full["terms"]["page_lines"]) == 7 and len(full["robots"]["text_lines"]) == 3


def test_codex_an_unwritable_receipt_is_refused_before_any_fetch(tmp_path, capsys, monkeypatch):
    ro = tmp_path / "ro.json"
    ro.write_text("{}")
    real = probe.os.access                                             # root may write anything: the check is simulated
    monkeypatch.setattr(probe.os, "access", lambda path, mode: False if Path(path) == ro else real(path, mode))
    fake = Fake(terms_pages())
    assert probe.main(["--terms-url", TERMS, "--out", str(ro)], get=fake) == probe.REFUSED
    assert fake.asked == [] and "not writable" in capsys.readouterr().out
    deep = tmp_path / "a" / "b" / "r.json"                           # a missing parent is made, then the run reads
    assert probe.main(["--terms-url", TERMS, "--out", str(deep)], get=Fake(terms_pages())) == probe.OK
    assert deep.exists()


def test_codex_every_line_with_no_status_word_is_kept_in_the_receipt(capsys, monkeypatch):
    text = ["Injury Report: 11/12/26 08:00 PM\n" + "".join(f"Filler line {i}\n" for i in range(30))
            + "Doe, John Suspended League\n"]
    monkeypatch.setattr(probe, "read_pdf_pages", lambda data: text)
    _, out, _, _ = run(capsys, ["--report", "--index-url", INDEX, "--terms-ruling", "addendum 999 item 1"],
                       report_pages())
    assert "| Doe, John Suspended League" not in out                  # the console keeps its sample cap
    f = probe.fields_report(text, probe.Out())
    assert "Doe, John Suspended League" in f["lines_no_status_word_all"] and len(f["lines_no_status_word_all"]) == 31


def test_codex_an_anchor_with_a_greater_than_in_a_quoted_attribute_is_read():
    links = probe.index_links('<a title="Latest > archived" href="/f/Injury-Report_2026-11-12_08PM.pdf">x</a>',
                              "https://reports.example.invalid/")
    assert [x["file"] for x in links] == ["Injury-Report_2026-11-12_08PM.pdf"] and links[0]["text"] == "x"




# ---- Codex's third round on #970: the P1 under addendum 360 item 2(b) (a line altered in the receipt) ----------------

CP1252_PAGE = ("<html><body><h1>Terms of Use</h1><p>Last Updated: June 1, 2026</p>"
               "<p>You may not use any robot or scraper — the League’s café rules.</p></body></html>")


def _page_text(rec):
    return [ln["text"] for ln in rec["terms"]["page_lines"]]


def test_codex_r3_the_http_charset_decodes_the_page_so_no_line_is_altered(capsys):
    pages = terms_pages()
    pages[TERMS] = (200, CP1252_PAGE.encode("cp1252"), {"Content-Type": "text/html; charset=windows-1252"})
    code, out, rec, _ = run(capsys, ["--terms-url", TERMS], pages)
    text = _page_text(rec)
    assert "You may not use any robot or scraper — the League’s café rules." in text
    assert not any("�" in t for t in text)
    assert rec["terms"]["encoding"] == "windows-1252" and rec["terms"]["encoding_source"].startswith("HTTP")


def test_codex_r3_a_meta_charset_decodes_the_page(capsys):
    pages = terms_pages()
    page = CP1252_PAGE.replace("<html>", '<html><head><meta charset="iso-8859-1"></head>')
    pages[TERMS] = (200, page.encode("cp1252"), {"Content-Type": "text/html"})
    code, out, rec, _ = run(capsys, ["--terms-url", TERMS], pages)
    assert "You may not use any robot or scraper — the League’s café rules." in _page_text(rec)
    assert rec["terms"]["encoding"] == "windows-1252"              # iso-8859-1 is read as windows-1252, as a browser does
    assert rec["terms"]["encoding_source"].startswith("<meta")


def test_codex_r3_an_undeclared_page_that_is_not_utf8_is_read_as_windows_1252_and_said(capsys):
    pages = terms_pages()
    pages[TERMS] = (200, CP1252_PAGE.encode("cp1252"), {"Content-Type": "text/html"})
    code, out, rec, _ = run(capsys, ["--terms-url", TERMS], pages)
    assert "You may not use any robot or scraper — the League’s café rules." in _page_text(rec)
    assert rec["terms"]["encoding"] == "windows-1252" and "not valid UTF-8" in rec["terms"]["encoding_source"]
    assert "not valid UTF-8" in out


def test_codex_r3_a_utf8_page_stays_utf8_and_a_bom_wins(capsys):
    pages = terms_pages()
    pages[TERMS] = (200, b"\xef\xbb\xbf" + CP1252_PAGE.encode("utf-8"), {"Content-Type": "text/html; charset=windows-1252"})
    code, out, rec, _ = run(capsys, ["--terms-url", TERMS], pages)
    assert "You may not use any robot or scraper — the League’s café rules." in _page_text(rec)
    assert rec["terms"]["encoding"] == "utf-8" and rec["terms"]["encoding_source"] == "BOM"


def test_codex_r3_robots_txt_honours_its_charset(capsys):
    pages = terms_pages()
    pages["https://terms.example.invalid/robots.txt"] = (200, "# café\nDisallow: /\n".encode("cp1252"),
                                                         {"Content-Type": "text/plain; charset=ISO-8859-1"})
    code, out, rec, _ = run(capsys, ["--terms-url", TERMS], pages)
    assert rec["robots"]["text_lines"][0]["text"] == "# café"
    assert rec["robots"]["encoding"] == "windows-1252"


# ---- ARCHITECT 2026-11-12, addendum 362: no redirect is followed (item 5); the console escapes control characters
# (item 7); the use words are indexed (item 9(i)) ----------------------------------------------------------------------

ROBOTS_URL = "https://terms.example.invalid/robots.txt"


def test_362_5_robots_redirecting_to_the_terms_url_is_printed_not_followed(capsys):
    pages = terms_pages()
    pages[ROBOTS_URL] = (301, b"", {"Location": TERMS})
    code, out, rec, fake = run(capsys, ["--terms-url", TERMS], pages)
    assert [u for u, _ in fake.asked] == [TERMS, ROBOTS_URL]           # exactly two GETs
    assert fake.follow_flags == [False, False]                         # every GET sent with redirects off
    assert f"HTTP 301 · REDIRECTED, not followed: Location {TERMS}" in out
    assert code == probe.REFUSED
    assert rec["robots"]["http"] == 301 and rec["robots"]["location"] == TERMS
    assert rec["redirects"] == [{"url": ROBOTS_URL, "http": 301, "location": TERMS}]
    assert "final_url" not in rec["robots"] and "final_url" not in rec["terms"]


def test_362_5_a_redirected_terms_page_ends_that_read_and_robots_is_still_read(capsys):
    pages = terms_pages()
    pages[TERMS] = (302, b"<html>moved</html>", {"Location": "https://elsewhere.example.invalid/terms"})
    code, out, rec, fake = run(capsys, ["--terms-url", TERMS], pages)
    assert [u for u, _ in fake.asked] == [TERMS, ROBOTS_URL] and fake.follow_flags == [False, False]
    assert "REDIRECTED, not followed: Location https://elsewhere.example.invalid/terms" in out
    assert "TERMS NOT READ" in out and code == probe.REFUSED
    assert "page_lines" not in rec["terms"] and rec["robots"]["lines"] == 3


def test_362_5_a_redirected_index_ends_the_report_phase(capsys):
    pages = {INDEX: (301, b"", {"Location": "https://reports.example.invalid/elsewhere"})}
    code, out, rec, fake = run(capsys, ["--report", "--index-url", INDEX, "--terms-ruling", "addendum 999 item 1"],
                               pages)
    assert [u for u, _ in fake.asked] == [INDEX] and fake.follow_flags == [False]
    assert code == probe.REFUSED and "links" not in rec


def test_362_7_control_characters_from_a_fetched_page_are_escaped_on_the_console_and_exact_in_the_receipt(capsys):
    pages = terms_pages()
    line = "You may not use a robot \x1b[2J\x1b]52;c;ZXZpbA==\x07 here\x7f\x9b."
    pages[TERMS] = (200, f"<html><body><h1>Terms</h1><p>{line}</p></body></html>".encode(), {"Content-Type": "text/html"})
    pages[ROBOTS_URL] = (200, b"Disallow: /x\x1b[31m\r\n", {"Location": "x"})
    code, out, rec, fake = run(capsys, ["--terms-url", TERMS], pages)
    for raw in ("\x1b", "\x07", "\x7f", "\x9b", "\r"):
        assert raw not in out
    assert "You may not use a robot \\x1b[2J\\x1b]52;c;ZXZpbA==\\x07 here\\x7f\\x9b." in out
    assert "  | Disallow: /x\\x1b[31m" in out
    assert line in [ln["text"] for ln in rec["terms"]["page_lines"]]      # the receipt keeps the text exact
    assert rec["robots"]["text_lines"][0]["text"] == "Disallow: /x\x1b[31m"


def test_362_7_the_escape_keeps_tab_and_text_and_escapes_c0_del_c1():
    assert probe.console_safe("a\tb") == "a\tb"
    assert probe.console_safe("\x00\x1f\n\x7f\x80\x9f\xa0é") == "\\x00\\x1f\\x0a\\x7f\\x80\\x9f\xa0é"


def test_362_9i_the_use_words_open_windows(capsys):
    pages = terms_pages()
    pages[TERMS] = (200, b"<html><body><h1>Terms</h1><p>Statistics may be used only for non-commercial purposes and "
                         b"not in connection with gambling or any wager.</p><p>A database needs our consent.</p>"
                         b"</body></html>", {"Content-Type": "text/html"})
    code, out, rec, fake = run(capsys, ["--terms-url", TERMS], pages)
    matched = {ln["text"] for w in rec["terms"]["windows_all"] for ln in w["lines"] if ln["match"]}
    assert matched == {"Statistics may be used only for non-commercial purposes and not in connection with gambling "
                       "or any wager.", "A database needs our consent."}


def test_362_5_the_location_prints_verbatim_not_as_a_repr(capsys):
    pages = terms_pages()
    loc = "https://elsewhere.example.invalid/a\\b\tc'd"
    pages[TERMS] = (302, b"", {"Location": loc})
    code, out, rec, fake = run(capsys, ["--terms-url", TERMS], pages)
    assert f"REDIRECTED, not followed: Location {loc}" in out              # one backslash, the tab kept, no quotes
    assert f"answered HTTP 302, Location {loc} " in out
    assert rec["terms"]["location"] == loc


def test_362_7_a_library_warning_carrying_document_text_is_escaped_on_stderr(capsys):
    import logging
    probe.main(["--terms-url", TERMS], get=Fake(terms_pages()))          # the run sets the console up
    capsys.readouterr()
    logging.getLogger("pypdf._reader").warning("Multiple definitions for key /X\x1b]0;PWNED\x07\x1b[31m\x9b")
    err = capsys.readouterr().err
    assert "\x1b" not in err and "\x07" not in err and "\x9b" not in err
    assert "/X\\x1b]0;PWNED\\x07\\x1b[31m\\x9b" in err


# ---- #972 items A and B (ARCHITECT 2026-11-12, addendum 363 item 6): the receipt keeps a line's characters ------------

def test_972_a_robots_lines_break_only_at_cr_lf_and_crlf(capsys):
    pages = terms_pages()
    served = "User-agent: *\r\nDisallow: /a\x1cb\x1d\x1e\x0bc\x0cd\x85e f\nAllow: /\r"
    pages[ROBOTS_URL] = (200, served.encode(), {})
    code, out, rec, fake = run(capsys, ["--terms-url", TERMS], pages)
    assert [ln["text"] for ln in rec["robots"]["text_lines"]] == [
        "User-agent: *", "Disallow: /a\x1cb\x1d\x1e\x0bc\x0cd\x85e f", "Allow: /"]
    assert rec["robots"]["lines"] == 3
    assert "  | Disallow: /a\\x1cb\\x1d\\x1e\\x0bc\\x0cd\\x85e f" in out    # the console shows them escaped


def test_972_a_pdf_text_lines_break_only_at_cr_lf_and_crlf():
    f = probe.fields_report(["Injury Report: 11/12/26 08:00 PM\r\nLast, First\x1cOut\x85 Injury\x0b\n"], probe.Out())
    assert f["lines"] == 2 and f["first_lines"] == ["Injury Report: 11/12/26 08:00 PM", "Last, First\x1cOut\x85 Injury\x0b"]


def test_972_b_the_page_folds_only_html_whitespace():
    lines = [ln["text"] for ln in probe.page_lines(
        "<p>No scraping\x01 of\x1fthe\x85site.</p><p>a \n\t\r\x0c  b</p><p>c\xa0\xa0d e</p>")]
    assert lines == ["No scraping\x01 of\x1fthe\x85site.", "a b", "c d e"]       # spaces fold as on main; controls kept


# ---- the first adversarial pass on the #972 A/B change: only the control characters are kept; every space (NBSP and
# the other Unicode spaces) folds and trims exactly as on main ----------------------------------------------------------

def test_972_pass1_an_nbsp_spacer_is_no_line_and_the_window_and_date_line_are_unchanged():
    page = ("<p>Last Updated:</p><p>&nbsp;</p><p>October 1, 2026</p><p>No robots or scrapers may access.</p>"
            "<p>&nbsp;</p><p>&nbsp;</p><p>Violators will be prosecuted.</p>")
    windows, updated, dropped, lines = probe.terms_windows(page)
    assert [ln["text"] for ln in lines] == ["Last Updated:", "October 1, 2026", "No robots or scrapers may access.",
                                            "Violators will be prosecuted."]
    assert probe.date_lines(lines)[0]["next"] == "October 1, 2026"
    assert windows[0]["lines"][-1]["text"] == "Violators will be prosecuted."


def test_972_pass1_a_page_of_only_nbsp_is_not_read(capsys):
    pages = terms_pages()
    pages[TERMS] = (200, "<html><body><p>&nbsp;</p><p>\xa0　</p></body></html>".encode(),
                    {"Content-Type": "text/html"})
    code, out, rec, fake = run(capsys, ["--terms-url", TERMS], pages)
    assert "the page parsed to 0 lines: NOT READ" in out and code == probe.FAILED


def test_972_pass1_pdf_lines_of_only_spaces_are_dropped_and_a_page_footer_is_not_a_body_line():
    f = probe.fields_report(["Injury Report: 11/12/26\n\xa0\n　\nJames, LeBron Out\nPage 1 of 2\xa0\n"
                             "\x85Page 2 of 2\x0b\n"], probe.Out())
    assert f["lines"] == 4 and f["first_lines"][:2] == ["Injury Report: 11/12/26", "James, LeBron Out"]
    assert f["lines_no_status_word_all"] == []
    assert probe.fields_report(["\xa0\n　\n"], probe.Out())["lines"] == 0


def test_972_pass1_index_link_text_folds_spaces_as_on_main():
    links = probe.index_links('<a href="/f/Injury-Report_2026-11-12_08PM.pdf">\xa0 Report\xa0\xa0 8 PM　</a>',
                              "https://reports.example.invalid/")
    assert links[0]["text"] == "Report 8 PM"
