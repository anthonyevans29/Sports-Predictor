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
    assert ('"You may not use any robot, spider, scraper or other automated means to access the Services."' in out)
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
    assert f["status_lines"]["Out"] == 1 and f["rows_no_status_word"] == 1
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
