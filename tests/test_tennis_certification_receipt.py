"""The tennis data certification receipt (scripts/tennis_certification_receipt.py; ARCHITECT 2026-11-06, addendum 269
items 1-3; 2026-11-07, addendum 284 item 1(b): "a certification receipt script on the pattern of the NBA's (served and
stored phases)"; #838). SYNTHETIC payloads only (tests/test_tennis_wiring.py's shapes); Kalshi is never called; the
stored phase reads a copy built under tmp_path, never data/."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
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
    assert "THE QUOTE IN CODE (addendum 288 item 3): kalshi_tennis.CONTRACT_TERMS_QUOTE, verbatim:" in atp
    for key, text in kt.CONTRACT_TERMS_QUOTE.items():
        assert f"      {key}: {json.dumps(text, ensure_ascii=False)}" in atp
    # the synthetic markets carry synthetic rules text: none carries the quoted clause, and the count says so
    assert "markets whose rules_secondary carries the quoted clause: 0 of 8 · whose early_close_condition is the " \
           "quoted one: 0 of 8" in atp
    assert atp.index("THE QUOTE IN CODE") < atp.index("THE MAP (addendum 269 item 3(b))")


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
        s.add_all([m("E1", MatchStatus.FINISHED, 0, 1, Result.HOME, {**sett, "kalshi_kickoff": "occurrence_datetime"}),
                   m("E2", MatchStatus.SETTLED_SCALAR, 2, 3, None, {**sett, "kalshi_kickoff": "START_UNREAD"}),
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
    assert ("by stored kickoff source (external_ids['kalshi_kickoff'], addendum 288 item 1; START_UNREAD rows are never "
            "captured): <none stored>: 2 · START_UNREAD: 1 · occurrence_datetime: 1") in out, out
    tail = json.loads(out.strip().splitlines()[-1].split(" ", 1)[1])
    assert tail["phase"] == "stored" and tail["tours"]["ATP"]["seasons"]["2026"]["rows"] == 4
    assert tail["tours"]["ATP"]["seasons"]["2026"]["kickoff_sources"] == {"<none stored>": 2, "START_UNREAD": 1,
                                                                   "occurrence_datetime": 1}, tail


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


def test_the_served_phase_prints_the_time_keys_and_the_ruled_kickoff_ahead_of_the_run(capsys):
    """THE TIMES (addendum 288 item 1, RULED; 5(c): "the kickoffs shown ahead of now"): every time key the stage-1
    digest lists as served, its offset in hours from 00:00 UTC of the ticker's date; the stored kickoff by source and
    the kickoff refusals by label; the events whose served kickoff's US Eastern day is not the ticker's date; the active
    markets with their stored (ruled) kickoff, ahead of or past the run. SYNTHETIC values."""
    ahead = (datetime.now(timezone.utc) + timedelta(days=3)).replace(hour=14, minute=0, second=0, microsecond=0)
    day = ahead.strftime("%y%b%d").upper()
    ev = pair(f"{day}EEEFFF", "Eli Sampleton", "Ana Synthwood")
    for m in ev:
        m.update(occurrence_datetime=ahead.strftime("%Y-%m-%dT%H:%M:%SZ"), open_time="2026-12-27T20:00:00Z")
    late = pair(f"{day}MMMNNN", "Max Lately", "Ned Lately")                 # past midnight ET: the next US Eastern day
    nxt = (ahead + timedelta(days=1)).replace(hour=5)
    for m in late:
        m.update(occurrence_datetime=nxt.strftime("%Y-%m-%dT%H:%M:%SZ"))
    bad = pair(f"{day}PPPQQQ", "Pia Twotimes", "Quin Twotimes")
    bad[0]["occurrence_datetime"], bad[1]["occurrence_datetime"] = "2026-12-29T14:00:00Z", "2026-12-29T15:30:00Z"
    unread = pair(f"{day}RRRSSS", "Rae Notime", "Sam Notime")
    code, out, _ = run(capsys, "--tour", "ATP", fake=provider(pages={("KXATPMATCH", "open"): [ev + late + bad + unread]}))
    assert code == R.OK, out
    t = out[out.index("THE TIMES"):out.index("  NULLS")]
    assert "the kickoff RULED, addendum 288 item 1" in t and kt.START_UNREAD_LABEL in t
    assert "occurrence_datetime: served on 4 of" in t and "+14: 2" in t and "open_time: served on 2 of" in t
    assert "close_time: served on 0 of" in t
    assert "+29: 2" in t                                    # the late event: 05:00Z of the next day
    assert "THE STORED KICKOFF by source (accepted events): START_UNREAD: 4 · occurrence_datetime: 2 · " \
           "expected_expiration_time: 0" in t, t
    assert f"events REFUSED by the kickoff rule (never a fixture), by label: {kt.OCCURRENCE_DIFFER}: 1" in t
    assert f"KXATPMATCH-{day}PPPQQQ: {kt.OCCURRENCE_DIFFER}" in t
    assert "kickoff's US Eastern day is NOT the ticker's date" in t and f"KXATPMATCH-{day}MMMNNN: ticker date" in t
    # three counts that partition the active markets: a START_UNREAD row is never counted ahead, whatever its instant
    assert ("active markets: 6 · a served kickoff ahead of this run: 4 · a served kickoff already past it (the capture "
            "refuses them as in play): 0 · on a START_UNREAD row (never captured, its UTC+14 instant ahead or not): 2") \
        in t, t
    assert (f"KXATPMATCH-{day}EEEFFF-AAA · ticker date {ahead.date()} · stored kickoff {ahead:%Y-%m-%d} 14:00Z "
            f"(occurrence_datetime; ahead of this run) · occurrence_datetime") in t, t
    assert "OPEN: no ruling names a tennis season" in out
    tail = json.loads(out.strip().splitlines()[-1].split(" ", 1)[1])
    atp = tail["tours"]["ATP"]
    assert atp["time_keys_served"]["occurrence_datetime"] == 4 and atp["active"] == 6 and atp["active_ahead"] == 4
    assert atp["active_ahead"] + atp["active_past_kickoff"] + atp["active_start_unread"] == atp["active"]
    assert atp["kickoff_sources"] == {"occurrence_datetime": 2, "expected_expiration_time": 0, "START_UNREAD": 4}
    assert atp["kickoff_refused"] == {kt.OCCURRENCE_DIFFER: 1} and atp["kickoff_et_day_not_ticker"] == 1
    assert atp["active_start_unread"] == 2
    assert "START_UNREAD (the stored kickoff is the UTC+14 instant, the row never captured; 288 item 1): 4 of 6" in out


def _mismatch(event, a, b, ea, eb, yes_first=True):
    """A finalized yes/no event whose expiration_values are (ea on a's market, eb on b's); a's market is 'yes'."""
    return pair(event, a, b, results=("yes", "no") if yes_first else ("no", "yes"), exps=(ea, eb), status="finalized")


def test_the_expiration_value_shapes_of_the_winner_mismatch_events_are_printed_verbatim(capsys):
    """ARCHITECT 2026-11-08, addendum 288 item 2(b): "a line per distinct expiration_value SHAPE on the unmapped events
    (the value verbatim, the count, the 'yes' player beside it for three samples)". settle()'s guard also fires when
    EVERY expiration_value is empty, so a shape is the PAIR (the 'yes' market's value, the 'no' market's), each classed
    as served: empty, the 'yes' market's player, the 'no' market's player, else the value itself verbatim (repr)."""
    settled = (_mismatch("26DEC20AAABBB", "Ana Synthwood", "Bea Fakely", "Yes", "Yes")
               + _mismatch("26DEC20CCCDDD", "Cal Mockton", "Dov Testerly", "Yes", "Yes")
               + _mismatch("26DEC20EEEFFF", "Eli Sampleton", "Fay Dummer", "", "")
               + _mismatch("26DEC20GGGHHH", "Gus Oldfield", "Hal Pastly", "hal pastly", "Hal Pastly")
               + _mismatch("26DEC20IIIJJJ", "Ivy Solo", "Jo Duo", " ", None)
               + _mismatch("26DEC20KKKLLL", "Kim Trialson", "Lea Pretendo", "Kim Trialson", "Kim Trialson")  # FINISHED
               + _mismatch("26DEC20MMMNNN", "Max Oldrow", "Ned Oldrow", "Oldrow", "")
               + _mismatch("26DEC20OOOPPP", "Oto Yes", "Pat Yes", "Yes", "Yes")
               + _mismatch("26DEC20QQQRRR", "Quin Yes", "Rae Yes", "Yes", "Yes"))
    code, out, _ = run(capsys, "--tour", "ATP", fake=provider(pages={("KXATPMATCH", "settled"): [settled]}))
    assert code == R.OK, out
    blk = out[out.index("THE expiration_value SHAPES"):out.index("SETTLED_SCALAR events:")]
    assert f"left SCHEDULED by {kt.WINNER_MISMATCH!r}" in blk, blk
    assert ("every shape printed: 8 event(s) (8 accepted · 0 refused by the kickoff rule, so not in the projection "
            "above) · 4 shape(s)") in blk, blk
    lines = blk.splitlines()
    assert [ln.strip() for ln in lines if ln.strip().startswith("[")] == [
        "[4] yes market: 'Yes' · no market: 'Yes'",                       # one token, one shape, its count
        f"[2] yes market: {R.EMPTY} · no market: {R.EMPTY}",              # every value empty: settle's any(exp) guard
        f"[1] yes market: 'Oldrow' · no market: {R.EMPTY}",
        f"[1] yes market: {R.NO_PLAYER} · no market: {R.NO_PLAYER}"]      # the other side's name, in two letter cases
    # the values verbatim (repr), empties, None and whitespace visible
    assert "values verbatim (yes / no): '' / '' [1] · ' ' / None [1]" in blk, blk
    assert "values verbatim (yes / no): 'hal pastly' / 'Hal Pastly' [1]" in blk
    # three samples per shape at most, the 'yes' market's player beside each
    yes_samples = [ln for ln in lines if "sample" in ln and "expiration_value 'Yes' / 'Yes'" in ln]
    assert len(yes_samples) == 3, yes_samples
    assert "sample KXATPMATCH-26DEC20AAABBB: the 'yes' market's player 'Ana Synthwood' · expiration_value 'Yes' / " \
           "'Yes'" in blk
    assert "KXATPMATCH-26DEC20KKKLLL" not in blk                       # FINISHED: not a mismatch
    tail = json.loads(out.strip().splitlines()[-1].split(" ", 1)[1])
    assert tail["tours"]["ATP"]["winner_mismatch_events"] == 8 and tail["tours"]["ATP"]["exp_shapes"] == 4


def test_every_expiration_value_shape_prints_even_past_the_distinct_cap(capsys):
    """288 item 2(b): "a line per distinct expiration_value SHAPE". A per-event value (a surname, say) makes each event
    its own shape; every shape line prints, past MAX_DISTINCT, and nothing is classed beyond what is served (no
    surname class: that would be inference before the read)."""
    n = R.MAX_DISTINCT + 5
    settled = []
    for i in range(n):
        a, b = f"Ana Synth{i:02d}", f"Bea Fake{i:02d}"
        settled += _mismatch(f"26DEC20{chr(65 + i // 26)}{chr(65 + i % 26)}AXYZ", a, b, f"Synth{i:02d}", f"Synth{i:02d}")
    code, out, _ = run(capsys, "--tour", "ATP", fake=provider(pages={("KXATPMATCH", "settled"): [settled]}))
    assert code == R.OK, out
    blk = out[out.index("THE expiration_value SHAPES"):out.index("SETTLED_SCALAR events:")]
    shape_lines = [ln.strip() for ln in blk.splitlines() if ln.strip().startswith("[")]
    assert len(shape_lines) == n and f"{n} event(s)" in blk and f"{n} shape(s)" in blk, blk
    assert "more shape(s), not printed" not in blk
    assert f"[1] yes market: 'Synth{n - 1:02d}' · no market: 'Synth{n - 1:02d}'" in shape_lines


def test_a_winner_mismatch_event_the_kickoff_rule_refuses_is_still_read_for_its_shape(capsys):
    """288 item 2(a)/(b): the SHAPES read every unmapped event. An event the kickoff rule refuses (two different
    occurrence_datetime instants) is never a fixture, so it is not in THE MAP's projection; its shape is still printed
    and counted apart, so the total reconciles with the map's count. The tail JSON carries both counts."""
    ok = _mismatch("26DEC20AAABBB", "Ana Synthwood", "Bea Fakely", "Yes", "Yes")
    ko = _mismatch("26DEC20CCCDDD", "Cal Mockton", "Dov Testerly", "Yes", "Yes")
    ko[0]["occurrence_datetime"], ko[1]["occurrence_datetime"] = "2026-12-20T14:00:00Z", "2026-12-20T15:30:00Z"
    code, out, _ = run(capsys, "--tour", "ATP", fake=provider(pages={("KXATPMATCH", "settled"): [ok + ko]}))
    assert code == R.OK, out
    blk = out[out.index("THE expiration_value SHAPES"):out.index("SETTLED_SCALAR events:")]
    assert "2 event(s) (1 accepted · 1 refused by the kickoff rule, so not in the projection above) · 1 shape(s)" \
        in blk, blk
    assert "[2] yes market: 'Yes' · no market: 'Yes'" in blk and "sample KXATPMATCH-26DEC20CCCDDD" in blk, blk
    assert f"left SCHEDULED, by reason: {kt.WINNER_MISMATCH}: 1" in out, out
    tail = json.loads(out.strip().splitlines()[-1].split(" ", 1)[1])
    atp = tail["tours"]["ATP"]
    assert atp["winner_mismatch_events"] == 2 and atp["winner_mismatch_kickoff_refused"] == 1


@pytest.mark.parametrize("raw,want", [("", R.EMPTY), (None, R.EMPTY), ("  ", R.EMPTY), ("ANA SYNTHWOOD", R.YES_PLAYER),
                                      ("bea fakely ", R.NO_PLAYER), ("Yes", "'Yes'"), ("Synthwood", "'Synthwood'"),
                                      (0, R.EMPTY), (1, "1")])
def test_an_expiration_value_is_classed_as_served_never_interpreted(raw, want):
    assert R.exp_class(raw, "Ana Synthwood", "Bea Fakely") == want
