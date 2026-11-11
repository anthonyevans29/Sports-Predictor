"""The hold procedure's chain search (docs/specs/hosting-h1.md section O, "How to find every chain"), run as written
on this checkout's chains.py, systemd units and T11 lists. ARCHITECT 2026-11-10 19:35 ET, addendum 333 item 3(i),
verbatim: "the search reads MLB_LAPTOP_ONLY and prints "the laptop's morning routine (the architect's block)" for
mlb-morning and mlb-preslate, never a host timer that is not enabled"; item 3(iii): "a hold on UNL, WCQ or Euro names
sp-intl-daily.timer (intl-sync) beside whatever the search finds; the search prints it for those codes." Read-only:
the recipe imports chains and sp_common and reads unit files; it opens no database."""
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RUNBOOK = ROOT / "docs" / "specs" / "hosting-h1.md"
ROUTINE = "the laptop's morning routine (the architect's block)"


def recipe() -> str:
    s = RUNBOOK.read_text(encoding="utf-8")
    i = s.index("        C=NCAA\n")
    j = s.index("        PY\n", i) + len("        PY\n")
    return textwrap.dedent(s[i:j]).replace("C=NCAA\n", 'C="$1"\n', 1)


@pytest.fixture(scope="module")
def search():
    body = recipe().replace("python3 -", f"{sys.executable} -", 1)
    out = {}

    def run(code):
        if code not in out:
            r = subprocess.run(["bash", "-c", body, "search", code], cwd=ROOT, capture_output=True, text=True)
            assert r.returncode == 0, r.stderr
            out[code] = r.stdout.splitlines()
        return out[code]
    return run


def chain(lines, name):
    hit = [ln for ln in lines if ln.startswith(f"{name}: ")]
    assert len(hit) == 1, (name, lines)
    return hit[0]


def test_mlb_laptop_chains_print_the_routine_never_a_held_off_host_timer(search):
    lines = search("MLB")
    for name in ("mlb-morning", "mlb-preslate"):
        ln = chain(lines, name)
        assert ln.endswith(f" · {ROUTINE}"), ln
        assert "sp-mlb-morning.timer" not in ln and "sp-mlb-preslate.timer" not in ln
    assert chain(lines, "mlb-history").endswith(" · sp-mlb-history.timer")
    assert "launchd closing watch (MLB)" in chain(lines, "mlb-closing")
    assert not any("sp-clv-capture.timer" in ln or "NO TRIGGER FOUND" in ln for ln in lines)


def test_no_mlb_laptop_only_timer_is_ever_printed(search):
    lists = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, 'deploy/hosting'); "
                            "from sp_common import t11_lists; print(' '.join(t11_lists()['MLB_LAPTOP_ONLY']))"],
                           cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    assert lists, "MLB_LAPTOP_ONLY is empty"
    for code in ("MLB", "NCAA", "PL", "NFL", "UNL"):
        assert not any(t in ln for ln in search(code) for t in lists), code


@pytest.mark.parametrize("code", ["UNL", "WCQ_EU", "UEFA_EURO", "UEFA_EURO_Q"])
def test_national_team_codes_name_the_intl_daily_timer(search, code):
    ln = chain(search(code), "intl-daily")
    assert ln == (f"intl-daily: intl-sync (no code on the step; it writes {code} through _upsert_match) · "
                  "sp-intl-daily.timer")


def test_wcq_as_the_ruling_words_it_names_the_seven_stored_codes(search):
    ln = chain(search("WCQ"), "intl-daily")
    assert ln == ("intl-daily: intl-sync (no code on the step; it writes WCQ_EU, WCQ_SA, WCQ_AF, WCQ_AS, WCQ_NA, "
                  "WCQ_OC and WCQ_IC (a WCQ hold names all seven) through _upsert_match) · sp-intl-daily.timer")


@pytest.mark.parametrize("code", ["ATP", "WTA"])
def test_a_held_timer_is_marked_never_printed_as_running(search, code):
    """THE HELD LIST (the set-check recipe's HELD= line): sp-tennis-daily is installed and never enabled."""
    ln = chain(search(code), "tennis-daily")
    assert ln.endswith(" · sp-tennis-daily.timer (on THE HELD LIST: not enabled on the host)"), ln


def test_every_held_timer_printed_is_marked(search):
    rb = RUNBOOK.read_text(encoding="utf-8")
    held = re.search(r'^ *HELD="([^"]*)"', rb, re.M).group(1).split()
    assert held, "the held list is empty"
    for code in ("ATP", "WTA", "MLB", "NCAA", "PL", "NFL", "UNL"):
        for ln in search(code):
            for t in held:
                if t in ln:
                    assert f"{t} (on THE HELD LIST: not enabled on the host)" in ln, ln


@pytest.mark.parametrize("code", ["NCAA", "PL", "NFL", "MLB", "EFL"])
def test_club_codes_print_no_intl_sync_line(search, code):
    assert not any("intl-sync" in ln for ln in search(code))


def test_the_intl_codes_match_the_intl_sync_competition_map():
    """The write path, not the step's name (333 item 3(iii)): the search's national-team codes are exactly the codes
    intl-sync writes, CODE_BY_NAME in intl_history.py (read from its source text, so no database is opened)."""
    src = (ROOT / "src" / "ingestion" / "intl_history.py").read_text(encoding="utf-8")
    block = src[src.index("CODE_BY_NAME = ("):]
    block = block[:block.index("\n)\n")]
    mapped = set(re.findall(r'\), "([A-Z][A-Z0-9_]*)"\),', block))
    assert {"UNL", "UEFA_EURO", "UEFA_EURO_Q", "WCQ_EU", "CNL", "FRIENDLIES_INT"} <= mapped, mapped
    rec = recipe()
    listed = set(re.findall(r'"([A-Z][A-Z0-9_]*)"', rec[rec.index("intl = "):rec.index("units = {}")]))
    assert listed - {"WCQ"} == mapped, (sorted(listed), sorted(mapped))


@pytest.mark.parametrize("code", ["CNL", "CNL_Q", "FRIENDLIES_INT", "WCQ_IC"])
def test_the_rest_of_the_write_path_names_intl_daily_too(search, code):
    assert chain(search(code), "intl-daily").endswith(" · sp-intl-daily.timer")


def test_the_existing_readouts_hold(search):
    lines = search("NCAA")
    assert chain(lines, "ncaa-market").endswith(" · sp-ncaa-market.timer")
    assert chain(lines, "ncaa-schedule").endswith(" · sp-ncaa-schedule.timer")
    assert chain(lines, "window").endswith(" · sp-window.timer")
    assert chain(lines, "weekly-fullseason").endswith(" · sp-weekly-fullseason.timer")
    assert "sp-closing-watch.timer (closing.py watch --family SOCCER)" in chain(search("PL"), "soccer-closing")
    assert "sp-closing-watch.timer (closing.py watch --family NFL)" in chain(search("NFL"), "nfl-closing")
