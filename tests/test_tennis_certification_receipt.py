"""The tennis data certification receipt (scripts/tennis_certification_receipt.py; ARCHITECT 2026-11-06, addendum 269
items 1-3; 2026-11-07, addendum 284 item 1(b): "a certification receipt script on the pattern of the NBA's (served and
stored phases)"; #838). SYNTHETIC payloads only (tests/test_tennis_wiring.py's shapes); Kalshi is never called; the
stored phase reads a copy built under tmp_path, never data/."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from scripts import tennis_certification_receipt as R
from src.adapters import kalshi_tennis as kt
from tests.test_tennis_wiring import FakeKalshi, pair

ROOT = Path(__file__).resolve().parents[1]

SERIES_ROWS = [
    {"ticker": "KXATPMATCH", "title": "ATP Tennis Match", "category": "Sports", "tags": ["Tennis"],
     "frequency": "custom", "fee_type": "quadratic_with_maker_fees", "fee_multiplier": 1,
     "contract_terms_url": "https://example.invalid/SYNTHETIC-ATP-terms.pdf",
     "contract_url": "https://example.invalid/SYNTHETIC-ATP.pdf"},
    {"ticker": "KXWTAMATCH", "title": "WTA Tennis Match", "category": "Sports", "tags": ["Tennis"],
     "frequency": "custom", "contract_terms_url": "https://example.invalid/SYNTHETIC-WTA-terms.pdf"},
    {"ticker": "KXUNITEDCUPMATCH", "title": "SYNTHETIC out-of-scope series"},
]


def provider(**over):
    settled = (pair("26DEC28AAABBB", "Ana Synthwood", "Bea Fakely", results=("no", "yes"),
                    exps=("Bea Fakely", "Bea Fakely"), status="finalized")
               + pair("26DEC28CCCDDD", "Cal Mockton", "Dov Testerly", results=("scalar", "scalar"),
                      values=("0.4000", "0.6000"), status="finalized")
               + pair("26DEC28GGGHHH", "Gus Oldfield", "Hal Pastly", results=("yes", "yes"),
                      exps=("Gus Oldfield", "Gus Oldfield"), status="finalized"))
    pages = {("KXATPMATCH", "settled"): [settled[:2], settled[2:]],
             ("KXATPMATCH", "open"): [pair("26DEC29EEEFFF", "Eli Sampleton", "Ana Synthwood")
                                      + pair("26DEC29IIIJJJ", "Ivy Solo", "Ivy Solo")],
             ("KXWTAMATCH", "open"): [pair("26DEC29KKKLLL", "Kim Trialson", "Lea Pretendo", series="KXWTAMATCH")]}
    pages.update(over.pop("pages", {}))
    return FakeKalshi(pages, series_rows=SERIES_ROWS, **over)


def run(capsys, *args, fake=None):
    fake = fake or provider()
    code = R.main(list(args), adapter=kt.KalshiTennisAdapter(get=fake))
    return code, capsys.readouterr().out, fake


def test_the_served_phase_prints_the_series_terms_before_the_map(capsys):
    code, out, fake = run(capsys)
    assert code == R.OK, out
    assert 'contract_terms_url: "https://example.invalid/SYNTHETIC-ATP-terms.pdf"' in out
    assert 'fee_type: "quadratic_with_maker_fees"' in out and "fee_multiplier: 1" in out
    atp = out[out.index("\nATP · KXATPMATCH"):out.index("\nWTA · KXWTAMATCH")]
    assert atp.index("THE CONTRACT TERMS") < atp.index("THE MAP (addendum 269 item 3(b))")
    assert '[8] "SYNTHETIC rules text"' in atp and '"SYNTHETIC condition"' in atp
    for word in ("no", "yes", "scalar", ""):
        assert f"rules_primary, one market with result {word!r}" in atp
    assert "NOT QUOTED IN CODE: kalshi_tennis.CONTRACT_TERMS_QUOTE is null" in atp


def test_the_listing_is_read_to_its_last_page_and_the_map_projection_counts_every_reason(capsys):
    code, out, fake = run(capsys)
    atp = out[out.index("\nATP · KXATPMATCH"):out.index("\nWTA · KXWTAMATCH")]
    assert 'pages {"open": 1, "closed": 1, "settled": 2}' in atp and "THE LISTING (/markets, each status" in atp
    assert "STATUS WORDS AS SERVED: finalized: 6 · active: 4" in atp
    assert "projected: SCHEDULED: 2 · FINISHED: 1 · SETTLED_SCALAR: 1" in atp
    assert f"left SCHEDULED, by reason: {kt.DISAGREE}: 1" in atp and "KXATPMATCH-26DEC28GGGHHH" in atp
    assert f"refused as fixtures, by reason: {kt.NOT_TWO_PLAYERS}: 1" in atp and "KXATPMATCH-26DEC29IIIJJJ" in atp
    assert "SETTLED_SCALAR events: 1 · their markets' settlement values: 2 kept, 2 distinct" in atp
    assert "2026: 4 · SCHEDULED: 2 · FINISHED: 1 · SETTLED_SCALAR: 1" in atp
    assert "FINISHED with no winner: 0 (must read 0)" in atp and kt.SCORES_NULL_LABEL in atp
    tail = json.loads(out.strip().splitlines()[-1].split(" ", 1)[1])
    assert tail["phase"] == "served" and tail["exit"] == 0
    assert tail["tours"]["ATP"]["projected"] == {"SCHEDULED": 2, "FINISHED": 1, "SETTLED_SCALAR": 1}
    # only the two tour series are ever read
    assert {p["series_ticker"] for path, p in fake.calls if path == "markets"} == {"KXATPMATCH", "KXWTAMATCH"}
    assert "CALLS: " in out


def test_a_cursor_left_refuses_that_tour_and_the_other_is_still_read(capsys):
    page = pair("26DEC28AAABBB", "Ana Synthwood", "Bea Fakely")
    fake = provider(pages={("KXATPMATCH", "settled"): [page, page]},
                    cursors={(("KXATPMATCH", "settled"), 0): "c1", (("KXATPMATCH", "settled"), 1): "c1"})
    code, out, _ = run(capsys, fake=fake)
    assert code == R.REFUSED and "cursor already read" in out
    assert "\nWTA · KXWTAMATCH" in out and "THE MAP" in out[out.index("\nWTA · KXWTAMATCH"):]


def test_a_series_the_listing_does_not_serve_is_refused(capsys):
    fake = provider()
    fake.series_rows = [r for r in SERIES_ROWS if r["ticker"] != "KXWTAMATCH"]
    code, out, _ = run(capsys, "--tour", "WTA", fake=fake)
    assert code == R.REFUSED and "REFUSED: the /series listing does not serve KXWTAMATCH" in out


def test_a_failed_call_is_exit_1(capsys):
    def boom(path, params=None):
        raise ConnectionError("synthetic")
    code = R.main(["--tour", "ATP"], adapter=kt.KalshiTennisAdapter(get=boom))
    out = capsys.readouterr().out
    assert code == R.FAILED and "FAILED: ATP: ConnectionError: synthetic" in out


def test_the_served_phase_imports_nothing_that_opens_the_database(tmp_path):
    db_dir = tmp_path / "never"
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "from scripts import tennis_certification_receipt as R\n"
        "from src.adapters import kalshi_tennis as kt\n"
        "from tests.test_tennis_certification_receipt import provider\n"
        "rc = R.main([], adapter=kt.KalshiTennisAdapter(get=provider()))\n"
        "print('DBMOD', 'src.db.database' in sys.modules, rc)\n" % str(ROOT))
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_dir / 'x.db'}"}
    res = subprocess.run([sys.executable, "-c", code], cwd=str(tmp_path), env=env, capture_output=True, text=True,
                         timeout=120)
    assert "DBMOD False 0" in res.stdout, res.stdout + res.stderr
    assert not db_dir.exists()


# ---- the stored phase ------------------------------------------------------------------------------------------------

def _copy(tmp_path) -> Path:
    """A synthetic stored ATP season in its own SQLite file (never the app's database, never under data/)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from src.db.schema import Base, Competition, Match, MatchStatus, Result, Sport, Team
    path = tmp_path / "copy.db"
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        comp = Competition(sport=Sport.TENNIS, code="ATP", name="ATP Tennis Match", area="World", type="LEAGUE",
                           external_ids={"kalshi_tennis": "KXATPMATCH"})
        ts = [Team(sport=Sport.TENNIS, name=f"Synthetic {i}", external_ids={"kalshi_tennis": f"ATP|synthetic {i}"})
              for i in range(6)]
        s.add_all([comp, *ts])
        s.flush()
        k = datetime(2026, 12, 27, 10, 0)
        sett = {"kalshi_settlement": {"T-A": {"result": "yes"}}}

        def m(ev, st, h, a, res=None, ext=None, hs=None, when=k):
            return Match(sport=Sport.TENNIS, competition_id=comp.id, season="2026", utc_date=when, status=st,
                         status_raw="finalized", home_team_id=ts[h].id, away_team_id=ts[a].id, full_time_result=res,
                         home_score=hs, external_ids={"kalshi_tennis": ev, **(ext or {})})
        s.add_all([m("E1", MatchStatus.FINISHED, 0, 1, Result.HOME, sett),
                   m("E2", MatchStatus.SETTLED_SCALAR, 2, 3, None, sett),
                   m("E3", MatchStatus.FINISHED, 4, 5, None, None, hs=2),                 # planted: three defects
                   m("E4", MatchStatus.SCHEDULED, 0, 2, when=datetime(2026, 11, 1))])
        s.commit()
    eng.dispose()
    return path


def test_the_stored_phase_counts_per_season_and_the_true_zero_checks(tmp_path, capsys):
    path = _copy(tmp_path)
    code = R.main(["--db", str(path), "--tour", "ATP"])
    out = capsys.readouterr().out
    assert code == R.OK, out
    assert "players stored (teams of sport TENNIS): 6" in out
    assert "ATP (stored): 4 rows · sport TENNIS: 4" in out
    assert "2026: 4 rows · by status: FINISHED: 2 · SCHEDULED: 1 · SETTLED_SCALAR: 1" in out
    assert "FINISHED with no winner: 1 (must read 0: TRUE ZERO)" in out
    assert "FINISHED with no settlement kept: 1 (must read 0" in out
    assert "SETTLED_SCALAR carrying a winner: 0 (must read 0" in out
    assert "a score stored (NULL AND LABELLED by 269 item 2): 1 (must read 0" in out
    assert "more than 2 days before this run (unsettled, or settled after the chain's window): 1" in out
    tail = json.loads(out.strip().splitlines()[-1].split(" ", 1)[1])
    assert tail["phase"] == "stored" and tail["tours"]["ATP"]["seasons"]["2026"]["rows"] == 4


def test_the_stored_phase_refuses_a_copy_with_a_sidecar_and_reads_nothing(tmp_path, capsys):
    path = _copy(tmp_path)
    (tmp_path / "copy.db-wal").write_text("")
    assert R.main(["--db", str(path)]) == R.REFUSED
    assert "sidecar" in capsys.readouterr().out


@pytest.mark.parametrize("bad", ["missing.db", ""])
def test_the_stored_phase_refuses_a_missing_copy(tmp_path, capsys, bad):
    assert R.main(["--db", str(tmp_path / bad) if bad else ""]) == R.REFUSED
    assert "REFUSED" in capsys.readouterr().out


def test_the_stored_phase_refuses_a_path_under_data_and_creates_nothing(capsys):
    """Law 5: a --db under the checkout's data/ is refused by resolved path, and nothing is created there."""
    target = ROOT / "data" / "never-made-by-a-test.db"
    existed = (ROOT / "data").exists()
    assert R.main(["--db", str(target)]) == R.REFUSED
    assert "REFUSED" in capsys.readouterr().out
    assert not target.exists() and (ROOT / "data").exists() == existed


def test_the_served_phase_prints_the_time_keys_beside_the_tickers_date_for_the_kickoff_ruling(capsys):
    """Review P1 (the kickoff is open for a ruling): THE TIMES prints every time key the stage-1 digest lists as served,
    its offset in hours from 00:00 UTC of the ticker's date, the active markets already past the stored kickoff (the
    capture refuses them as in play), and the active markets with every time key verbatim. SYNTHETIC values."""
    ev = pair("26DEC29EEEFFF", "Eli Sampleton", "Ana Synthwood")
    for m in ev:
        m.update(occurrence_datetime="2026-12-29T09:00:00Z", open_time="2026-12-27T20:00:00Z")
    code, out, _ = run(capsys, "--tour", "ATP", fake=provider(pages={("KXATPMATCH", "open"): [ev]}))
    assert code == R.OK, out
    t = out[out.index("THE TIMES"):out.index("  NULLS")]
    assert "occurrence_datetime: served on 2 of" in t and "+9: 2" in t and "open_time: served on 2 of" in t
    assert "close_time: served on 0 of" in t
    assert "active markets: 2 · already past the stored kickoff at this run" in t
    assert ('KXATPMATCH-26DEC29EEEFFF-AAA · ticker date 2026-12-29 · stored kickoff 2026-12-28 10:00Z · '
            'occurrence_datetime "2026-12-29T09:00:00Z"') in t
    assert "OPEN: no ruling names a tennis season" in out
    tail = json.loads(out.strip().splitlines()[-1].split(" ", 1)[1])
    atp = tail["tours"]["ATP"]
    assert atp["time_keys_served"]["occurrence_datetime"] == 2 and atp["active"] == 2
