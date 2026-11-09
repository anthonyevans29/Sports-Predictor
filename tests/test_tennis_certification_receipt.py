"""The tennis data certification receipt (scripts/tennis_certification_receipt.py; ARCHITECT 2026-11-06, addendum 269
items 1-3; 2026-11-07, addendum 284 item 1(b): "a certification receipt script on the pattern of the NBA's (served and
stored phases)"; #838). SYNTHETIC payloads only (tests/test_tennis_wiring.py's shapes); Kalshi is never called; the
stored phase reads a copy built under tmp_path, never data/."""
from __future__ import annotations

import json
import os
import stat
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
                   m("E4", MatchStatus.SCHEDULED, 0, 2, when=datetime(2026, 11, 1)),
                   # 294 item 13(b): a held row whose event a sync refused carries the refusal label in the same key
                   m("E5", MatchStatus.FINISHED, 1, 3, Result.AWAY,
                     {**sett, "kalshi_kickoff": kt.OCCURRENCE_DIFFER})])
        s.commit()
    eng.dispose()
    return path


def test_the_stored_phase_counts_per_season_and_the_true_zero_checks(tmp_path, capsys):
    path = _copy(tmp_path)
    code = R.main(["--db", str(path), "--tour", "ATP"])
    out = capsys.readouterr().out
    assert code == R.OK, out
    assert "players stored (teams of sport TENNIS): 6" in out
    assert "ATP (stored): 5 rows · sport TENNIS: 5" in out
    assert "2026: 5 rows · by status: FINISHED: 3 · SCHEDULED: 1 · SETTLED_SCALAR: 1" in out
    assert "FINISHED with no winner: 1 (must read 0: TRUE ZERO)" in out
    assert "FINISHED with no settlement kept: 1 (must read 0" in out
    assert "SETTLED_SCALAR carrying a winner: 0 (must read 0" in out
    assert "a score stored (NULL AND LABELLED by 269 item 2): 1 (must read 0" in out
    assert "more than 2 days before this run (unsettled, or settled after the chain's window): 1" in out
    # 297 item B.12: the line's text "adds "and refusal labels (294 item 13(b))"", and the line counts them: the refusal
    # label is counted verbatim beside the sources (one key, one Counter), and the labelled rows on their own
    assert ("by stored kickoff source and refusal labels (294 item 13(b)) (external_ids['kalshi_kickoff'], addendum "
            "288 item 1; START_UNREAD rows are never captured): <none stored>: 2 · START_UNREAD: 1 · "
            f"occurrence_datetime: 1 · {kt.OCCURRENCE_DIFFER}: 1 · rows carrying a refusal label (never captured): "
            "1") in out, out
    tail = json.loads(out.strip().splitlines()[-1].split(" ", 1)[1])
    assert tail["phase"] == "stored" and tail["tours"]["ATP"]["seasons"]["2026"]["rows"] == 5
    assert tail["tours"]["ATP"]["seasons"]["2026"]["kickoff_sources"] == {"<none stored>": 2, "START_UNREAD": 1,
                                                                   "occurrence_datetime": 1,
                                                                   kt.OCCURRENCE_DIFFER: 1}, tail
    assert tail["tours"]["ATP"]["seasons"]["2026"]["kickoff_refusal_labelled"] == 1, tail


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


def test_the_map_counts_result_word_echo_per_tour_and_the_name_variant_stays_listed(capsys):
    """ARCHITECT 2026-11-08, addendum 296 item 2: a 'Yes' / 'No' event is FINISHED by branch (b), "counted under a label
    of its own, RESULT_WORD_ECHO, and printed by the receipt's MAP"; the name variant of SHAPE 2 (HANDAM: 'Martin
    Damm' on both against the yes market's 'Martin Damm Jr') "stay[s] SCHEDULED, listed". The header names both
    branches; the SHAPES keep listing what is still WINNER_MISMATCH. BAEMAC's date and both events' other player are
    SYNTHETIC placeholders (the ruling names neither)."""
    settled = (_mismatch("26OCT20BAEMAC", "Tomas Machac", "Bae Placeholder", "Yes", "No")
               + _mismatch("26OCT20CCCDDD", "Cal Mockton", "Dov Testerly", " yes", "NO ")
               + _mismatch("26OCT19HANDAM", "Martin Damm Jr", "Han Placeholder", "Martin Damm", "Martin Damm")
               + _mismatch("26OCT20EEEFFF", "Eli Sampleton", "Fay Dummer", "Eli Sampleton", "Eli Sampleton")
               + _mismatch("26OCT20GGGHHH", "Gus Oldfield", "Hal Pastly", "Yes", ""))
    wta = _mismatch("26OCT20KKKLLL", "Kim Trialson", "Lea Pretendo", "Yes", "No")
    for m in wta:
        m["event_ticker"] = m["event_ticker"].replace("KXATPMATCH", "KXWTAMATCH")
        m["ticker"] = m["ticker"].replace("KXATPMATCH", "KXWTAMATCH")
    code, out, _ = run(capsys, fake=provider(pages={("KXATPMATCH", "settled"): [settled],
                                                    ("KXWTAMATCH", "settled"): [wta]}))
    assert code == R.OK, out
    atp = out[out.index("\nATP · KXATPMATCH"):out.index("\nWTA · KXWTAMATCH")]
    wtab = out[out.index("\nWTA · KXWTAMATCH"):]
    head = atp[atp.index("THE MAP (addendum 269 item 3(b))"):atp.index("projected:")]
    assert "(a) expiration_value is the 'yes' market's player" in head, head
    assert ("(b) the 'yes' market's expiration_value reads 'Yes' and the 'no' market's 'No', case-insensitive after "
            "stripping, both holding (addendum 296 item 2: RESULT_WORD_ECHO, counted below)") in " ".join(head.split())
    # the settled page replaces the provider's: FINISHED = BAEMAC, CCCDDD (b) and EEEFFF (a); SCHEDULED = HANDAM,
    # GGGHHH and the provider's open event
    assert "projected: FINISHED: 3 · SCHEDULED: 3" in atp, atp
    assert f"FINISHED by branch (b), {kt.RESULT_WORD_ECHO}: 2 of 3 FINISHED (the rest by branch (a))" in atp, atp
    assert f"FINISHED by branch (b), {kt.RESULT_WORD_ECHO}: 1 of 1 FINISHED (the rest by branch (a))" in wtab, wtab
    # HANDAM and the 'Yes' / '' pair stay SCHEDULED by WINNER_MISMATCH, listed, and their shapes are printed
    assert f"KXATPMATCH-26OCT19HANDAM: {kt.WINNER_MISMATCH}" in atp and f"KXATPMATCH-26OCT20GGGHHH: " \
        f"{kt.WINNER_MISMATCH}" in atp, atp
    assert "KXATPMATCH-26OCT20BAEMAC:" not in atp                       # FINISHED: never in the SCHEDULED listing
    blk = atp[atp.index("THE expiration_value SHAPES"):atp.index("SETTLED_SCALAR events:")]
    assert "every shape printed: 2 event(s)" in blk and "'Martin Damm' / 'Martin Damm'" in blk, blk
    assert "BAEMAC" not in blk and "CCCDDD" not in blk
    tail = json.loads(out.strip().splitlines()[-1].split(" ", 1)[1])
    assert tail["tours"]["ATP"]["result_word_echo"] == 2 and tail["tours"]["WTA"]["result_word_echo"] == 1
    assert tail["tours"]["ATP"]["projected"]["FINISHED"] == 3 and tail["tours"]["WTA"]["projected"] == {"FINISHED": 1,
                                                                                                         "SCHEDULED": 1}


# ---- --tickers: the accepted event tickers per tour (ARCHITECT 2026-11-09, addendum 308 item 1(c); #905) ----------------

ATP_ACCEPTED = ["KXATPMATCH-26DEC28AAABBB", "KXATPMATCH-26DEC28CCCDDD", "KXATPMATCH-26DEC28GGGHHH",
                "KXATPMATCH-26DEC29EEEFFF"]


def _tail(out: str) -> dict:
    return json.loads(out.strip().splitlines()[-1].split(" ", 1)[1])


def test_tickers_writes_one_file_per_tour_sorted_one_per_line_the_accepted_events_only(tmp_path, capsys):
    """308 item 1(c): "the served phase takes `--tickers PATH` and writes the accepted event tickers per tour, one per
    line, sorted". The accepted events are the fixtures THE MAP projects (GGGHHH, left SCHEDULED by DISAGREE, is one);
    IIIJJJ, refused as a fixture (NOT_TWO_PLAYERS), and an event the kickoff rule refuses are not in it. Nothing but
    event tickers: no price, no name; no temporary file is left beside the dump."""
    ko = pair("26DEC27MMMNNN", "Max Synthor", "Ned Fakeson")
    ko[0]["occurrence_datetime"], ko[1]["occurrence_datetime"] = "2026-12-27T14:00:00Z", "2026-12-27T15:30:00Z"
    fake = provider(pages={("KXATPMATCH", "closed"): [ko]})
    prefix = tmp_path / "tennis_tickers_2026-11-10"
    code, out, _ = run(capsys, "--tickers", str(prefix), fake=fake)
    assert code == R.OK, out
    assert "KXATPMATCH-26DEC27MMMNNN" in out and "KXATPMATCH-26DEC29IIIJJJ" in out      # both read, both refused
    atp, wta = tmp_path / "tennis_tickers_2026-11-10.ATP.txt", tmp_path / "tennis_tickers_2026-11-10.WTA.txt"
    assert sorted(p.name for p in tmp_path.iterdir()) == [atp.name, wta.name]           # no temporary file left
    assert atp.read_bytes() == ("\n".join(ATP_ACCEPTED) + "\n").encode("ascii")
    assert wta.read_bytes() == b"KXWTAMATCH-26DEC29KKKLLL\n"
    text = atp.read_text()
    assert "IIIJJJ" not in text and "MMMNNN" not in text
    assert text.splitlines() == sorted(text.splitlines())
    um = os.umask(0)
    os.umask(um)
    for f in (atp, wta):                                                                # the umask's default, not 0600
        assert stat.S_IMODE(f.stat().st_mode) == 0o666 & ~um
    for name in ("Synthwood", "Fakely", "0.4", "Gus"):                                  # no name, no price
        assert name not in text
    assert f"TICKERS: wrote {atp} · 4 ATP event tickers (accepted events; sorted; one per line)" in out
    assert f"TICKERS: wrote {wta} · 1 WTA event tickers (accepted events; sorted; one per line)" in out
    tail = _tail(out)
    assert tail["exit"] == 0 and tail["tickers_written"] == {"ATP": 4, "WTA": 1}
    assert "KXATPMATCH-26DEC28AAABBB" not in out.strip().splitlines()[-1]                # the tail stays counts only
    # the dump's count is the accepted events' count the receipt prints
    assert tail["tours"]["ATP"]["events"] == 4 and tail["tours"]["WTA"]["events"] == 1


@pytest.mark.skipif(not __import__("shutil").which("comm"), reason="comm not installed")
def test_two_days_dumps_diff_by_comm(tmp_path, capsys):
    """308 item 1(c): "so a day-to-day listing diff is a `comm` of two files". Day 2's listing has lost a settled
    event (the erosion of item 1): `comm -23 day1 day2` lists it and nothing else; `comm -13` (new on day 2) lists the
    event that is new; the files compare as sorted (comm's --check-order passes, LC_ALL=C)."""
    run(capsys, "--tickers", str(tmp_path / "d1"))
    settled2 = (pair("26DEC28CCCDDD", "Cal Mockton", "Dov Testerly", results=("scalar", "scalar"),
                     values=("0.4000", "0.6000"), status="finalized")
                + pair("26DEC28GGGHHH", "Gus Oldfield", "Hal Pastly", results=("yes", "yes"),
                       exps=("Gus Oldfield", "Gus Oldfield"), status="finalized"))
    new = pair("26DEC30OOOPPP", "Oli Synthe", "Pat Fakir")
    fake2 = provider(pages={("KXATPMATCH", "settled"): [settled2],
                            ("KXATPMATCH", "open"): [pair("26DEC29EEEFFF", "Eli Sampleton", "Ana Synthwood") + new]})
    code, out, _ = run(capsys, "--tickers", str(tmp_path / "d2"), fake=fake2)
    assert code == R.OK, out
    env = {**os.environ, "LC_ALL": "C"}

    def comm(flag):
        res = subprocess.run(["comm", "--check-order", flag, str(tmp_path / "d1.ATP.txt"), str(tmp_path / "d2.ATP.txt")],
                             capture_output=True, text=True, env=env, timeout=30)
        assert res.returncode == 0, res.stderr
        return res.stdout
    assert comm("-23") == "KXATPMATCH-26DEC28AAABBB\n"                                  # left the listing
    assert comm("-13") == "KXATPMATCH-26DEC30OOOPPP\n"                                  # new on day 2
    assert (tmp_path / "d1.WTA.txt").read_text() == (tmp_path / "d2.WTA.txt").read_text()


@pytest.mark.parametrize("how", ["data", "Data", "checkout-data", "missing-parent", "directory", "dot", "dotdot",
                                 "trailing-slash", "with-db"])
def test_tickers_refusals_write_nothing_and_call_nothing(tmp_path, capsys, monkeypatch, how):
    """308 item 1(c) and law 5: a PATH under a data/ directory (any part named data, case ignored; the checkout's
    data/), a PATH whose directory does not exist (nothing is made), a directory, and --tickers outside the SERVED
    phase (with --db) are REFUSED, exit 2, before any call; nothing is written anywhere."""
    before = set(tmp_path.rglob("*"))
    extra: list[str] = []
    if how in ("data", "Data"):
        (tmp_path / how).mkdir()
        before = set(tmp_path.rglob("*"))
        path = str(tmp_path / how / "t")
    elif how == "checkout-data":
        path = str(ROOT / "data" / "t")                                                 # refused before any write
    elif how == "missing-parent":
        path = str(tmp_path / "nope" / "t")
    elif how == "directory":
        path = str(tmp_path)
    elif how in ("dot", "dotdot"):                                                      # '.' has no name: refused, no crash
        (tmp_path / "w").mkdir()
        before = set(tmp_path.rglob("*"))
        monkeypatch.chdir(tmp_path / "w")
        path = "." if how == "dot" else ".."
    elif how == "trailing-slash":
        path = str(tmp_path / "t") + "/"
    else:
        path = str(tmp_path / "t")
        extra = ["--db", str(tmp_path / "copy.db")]
    fake = provider()
    code, out, _ = run(capsys, "--tickers", path, *extra, fake=fake)
    assert code == R.REFUSED, out
    assert "REFUSED: --tickers" in out and "nothing read, nothing written" in out, out
    assert fake.calls == []                                                             # refused before any call
    assert set(tmp_path.rglob("*")) == before
    assert not (tmp_path / "nope").exists()
    assert not list((ROOT / "data").glob("t.*.txt")) if (ROOT / "data").exists() else True
    tail = _tail(out)
    assert tail["exit"] == R.REFUSED and tail["phase"] == ("stored" if how == "with-db" else "served")
    if how == "with-db":
        assert "not with --db (the STORED phase)" in out
    if how in ("data", "Data", "checkout-data"):
        assert "under a data/ directory (law 5)" in out
    if how == "missing-parent":
        assert "does not exist (nothing is made)" in out
    if how in ("directory", "dot", "dotdot"):
        assert "is a directory; name a file prefix" in out


def test_nothing_is_written_without_tickers(tmp_path, capsys, monkeypatch):
    """Without --tickers the served phase writes nothing (the receipt's "Writes nothing" stands) and the tail carries
    no tickers_written key."""
    monkeypatch.chdir(tmp_path)
    code, out, _ = run(capsys)
    assert code == R.OK, out
    assert list(tmp_path.iterdir()) == []
    assert "TICKERS:" not in out and "tickers_written" not in _tail(out)


def test_a_tour_whose_read_refused_writes_no_file_the_other_tour_is_written(tmp_path, capsys):
    """A cursor left refuses ATP's listing (269 item 3(d)): no ATP file (a partial listing is never dumped), the line
    says so; WTA's read answered and its file is written; the exit stays REFUSED."""
    page = pair("26DEC28AAABBB", "Ana Synthwood", "Bea Fakely")
    fake = provider(pages={("KXATPMATCH", "settled"): [page, page]},
                    cursors={(("KXATPMATCH", "settled"), 0): "c1", (("KXATPMATCH", "settled"), 1): "c1"})
    code, out, _ = run(capsys, "--tickers", str(tmp_path / "d"), fake=fake)
    assert code == R.REFUSED, out
    assert not (tmp_path / "d.ATP.txt").exists()
    assert "TICKERS: ATP: not written (the tour's read did not answer; no partial listing is dumped)" in out
    assert (tmp_path / "d.WTA.txt").read_text() == "KXWTAMATCH-26DEC29KKKLLL\n"
    assert _tail(out)["tickers_written"] == {"WTA": 1}


def test_a_failed_write_leaves_the_old_file_and_no_temporary_file(tmp_path, capsys, monkeypatch):
    """Atomic: the dump is written beside the target and renamed. A rename that fails leaves the previous file as it
    was and removes the temporary one; the run exits FAILED and says which file."""
    old = tmp_path / "d.ATP.txt"
    old.write_text("KXATPMATCH-OLD\n")

    def boom(src, dst):
        raise OSError("synthetic rename failure")
    monkeypatch.setattr(R.os, "replace", boom)
    code, out, _ = run(capsys, "--tour", "ATP", "--tickers", str(tmp_path / "d"))
    assert code == R.FAILED, out
    assert f"TICKERS: FAILED: ATP: {old}: OSError: synthetic rename failure" in out
    assert old.read_text() == "KXATPMATCH-OLD\n"
    assert [p.name for p in tmp_path.iterdir()] == ["d.ATP.txt"]


def test_the_docs_name_the_tickers_flag():
    doc = (ROOT / "docs" / "CLI.md").read_text()
    row = next(ln for ln in doc.splitlines() if ln.startswith("| `python3 scripts/tennis_certification_receipt.py` |"))
    assert "`[--tickers PATH]`" in row and "addendum 308 item 1(c)" in row and "#905" in row
    assert "`PATH.ATP.txt` and `PATH.WTA.txt`" in row and "comm -23" in row
    assert "--tickers PATH" in R.__doc__ and "addendum 308 item 1(c)" in R.__doc__


# ---- THE WINDOW LINE: counts by our status for a ticker-date range (ARCHITECT 2026-11-09, addendum 309 item 6) -------

def _edges():
    """ATP: the provider's 26DEC28 (FINISHED, SETTLED_SCALAR, SCHEDULED by DISAGREE) and 26DEC29 (SCHEDULED; IIIJJJ
    refused as a fixture) events, plus one FINISHED on 26DEC30 (the --through edge), one FINISHED on 26DEC27 (a day
    before --from) and one SETTLED_SCALAR on 26DEC31 (a day after --through)."""
    edge = (pair("26DEC30OOOPPP", "Oto Edgely", "Pia Boundson", results=("yes", "no"),
                 exps=("Oto Edgely", "Oto Edgely"), status="finalized")
            + pair("26DEC27QQQRRR", "Quin Earlyton", "Rex Beforely", results=("yes", "no"),
                   exps=("Quin Earlyton", "Quin Earlyton"), status="finalized")
            + pair("26DEC31SSSTTT", "Sol Lateman", "Tia Afterson", results=("scalar", "scalar"),
                   values=("0.5000", "0.5000"), status="finalized"))
    return provider(pages={("KXATPMATCH", "closed"): [edge]})


def test_the_window_line_counts_the_accepted_events_by_status_inside_inclusive_bounds(capsys):
    """309 item 6: "the served phase prints, per tour, the counts by our status for a ticker-date range". Both bounds
    are inclusive (26DEC28 and 26DEC30 counted); an event one day outside either bound (26DEC27, 26DEC31) is not; the
    refused IIIJJJ is no accepted event, so not counted."""
    code, out, _ = run(capsys, "--from", "2026-12-28", "--through", "2026-12-30", fake=_edges())
    assert code == R.OK, out
    lines = out.splitlines()
    assert ("ATP WINDOW 2026-12-28..2026-12-30 (ticker dates): FINISHED 2 · SETTLED_SCALAR 1 · SCHEDULED 2 "
            "(of 5 accepted events in the window)") in lines
    assert ("WTA WINDOW 2026-12-28..2026-12-30 (ticker dates): FINISHED 0 · SETTLED_SCALAR 0 · SCHEDULED 1 "
            "(of 1 accepted events in the window)") in lines
    assert sum(1 for ln in lines if " WINDOW " in ln and ln.startswith(("ATP", "WTA"))) == 2      # one line per tour
    tail = _tail(out)
    assert tail["window"] == {
        "from": "2026-12-28", "through": "2026-12-30", "default": [],
        "tours": {"ATP": {"FINISHED": 2, "SETTLED_SCALAR": 1, "SCHEDULED": 2, "accepted": 5},
                  "WTA": {"FINISHED": 0, "SETTLED_SCALAR": 0, "SCHEDULED": 1, "accepted": 1}}}
    assert tail["tours"]["ATP"]["events"] == 7                       # the whole listing's accepted events, 2 outside
    # a one-day window on each edge: the bound itself counts
    code, out, _ = run(capsys, "--from", "2026-12-27", "--through", "2026-12-27", fake=_edges())
    assert ("ATP WINDOW 2026-12-27..2026-12-27 (ticker dates): FINISHED 1 · SETTLED_SCALAR 0 · SCHEDULED 0 "
            "(of 1 accepted events in the window)") in out.splitlines()
    code, out, _ = run(capsys, "--from", "2026-12-31", "--through", "2026-12-31", fake=_edges())
    assert ("ATP WINDOW 2026-12-31..2026-12-31 (ticker dates): FINISHED 0 · SETTLED_SCALAR 1 · SCHEDULED 0 "
            "(of 1 accepted events in the window)") in out.splitlines()


def test_the_window_counts_the_same_set_as_the_tickers_dump(tmp_path, capsys):
    """The window counts the accepted events, the set --tickers dumps: over the whole listing's days the window's
    total is the dump's line count."""
    code, out, _ = run(capsys, "--from", "2026-12-01", "--through", "2026-12-31", "--tickers", str(tmp_path / "d"),
                       fake=_edges())
    assert code == R.OK, out
    tail = _tail(out)
    for tour in ("ATP", "WTA"):
        dumped = (tmp_path / f"d.{tour}.txt").read_text().splitlines()
        assert tail["window"]["tours"][tour]["accepted"] == len(dumped) == tail["tickers_written"][tour]
    assert "IIIJJJ" not in (tmp_path / "d.ATP.txt").read_text()


def test_the_default_window_is_the_daily_chains_yesterday_through_tomorrow_in_utc(capsys, monkeypatch):
    """Default, the daily window: tennis-daily's sync-matches --date-from {yesterday} --date-to {tomorrow}
    (deploy/hosting/chains.py; sp_run.date_vars, UTC). With today 2026-12-29: 2026-12-28..2026-12-30."""
    from datetime import date
    monkeypatch.syspath_prepend(str(ROOT / "deploy" / "hosting"))
    import chains
    import sp_run
    dv = sp_run.date_vars(date(2026, 12, 29))
    assert R.daily_window(date(2026, 12, 29)) == (date.fromisoformat(dv["yesterday"]),
                                                  date.fromisoformat(dv["tomorrow"]))
    sm = [s for s in chains.CHAINS["tennis-daily"]["steps"] if s[0] == "sync-matches"]
    assert len(sm) == 2 and all(s[s.index("--date-from") + 1] == "{yesterday}"
                                and s[s.index("--date-to") + 1] == "{tomorrow}" for s in sm)
    monkeypatch.setattr(R, "utc_today", lambda: date(2026, 12, 29))
    code, out, _ = run(capsys, fake=_edges())
    assert code == R.OK, out
    assert ("ATP WINDOW 2026-12-28..2026-12-30 (ticker dates): FINISHED 2 · SETTLED_SCALAR 1 · SCHEDULED 2 "
            "(of 5 accepted events in the window)") in out.splitlines()
    assert "the daily window, tennis-daily {yesterday}..{tomorrow} in UTC" in out
    tail = _tail(out)
    assert tail["window"]["from"] == "2026-12-28" and tail["window"]["through"] == "2026-12-30"
    assert tail["window"]["default"] == ["from", "through"]
    # both given: the header says so and no bound is the daily window's
    code, out, _ = run(capsys, "--from", "2026-12-28", "--through", "2026-12-30", fake=_edges())
    assert "both bounds inclusive; --from and --through given)" in out
    assert _tail(out)["window"]["default"] == []


@pytest.mark.parametrize("args, span, header, default", [
    (["--through", "2026-12-31"], "2026-12-28..2026-12-31",
     "--through given; --from the daily window's, tennis-daily's {yesterday} in UTC", ["from"]),
    (["--from", "2026-12-27"], "2026-12-27..2026-12-30",
     "--from given; --through the daily window's, tennis-daily's {tomorrow} in UTC", ["through"]),
])
def test_a_lone_bound_is_named_given_and_the_other_the_daily_windows(capsys, monkeypatch, args, span, header,
                                                                      default):
    """A lone bound takes the other from the daily window, and the header and the tail name which was given and
    which came from the daily window (never 'given' for the pair, never default false)."""
    from datetime import date
    monkeypatch.setattr(R, "utc_today", lambda: date(2026, 12, 29))
    code, out, _ = run(capsys, *args, fake=_edges())
    assert code == R.OK, out
    assert f"ATP WINDOW {span} (ticker dates)" in out
    assert f"both bounds inclusive; {header})" in out
    w = _tail(out)["window"]
    assert f"{w['from']}..{w['through']}" == span and w["default"] == default


def test_the_default_window_is_worked_out_before_any_call_once_per_run(capsys, monkeypatch):
    """The default window is worked out at the start, before the first call (sp_run computes {yesterday}/{tomorrow}
    once at the chain's start): a run that crosses 00:00Z keeps the window it started with."""
    from datetime import date
    fake = _edges()
    seen = []

    def today():
        seen.append(len(fake.calls))
        return date(2026, 12, 29) if len(seen) == 1 else date(2026, 12, 30)       # 00:00Z passes after the first

    monkeypatch.setattr(R, "utc_today", today)
    code, out, _ = run(capsys, fake=fake)
    assert code == R.OK, out
    assert seen == [0], seen                                 # once, with no call made yet
    assert fake.calls                                        # the reads did run after it
    w = _tail(out)["window"]
    assert (w["from"], w["through"]) == ("2026-12-28", "2026-12-30")
    assert "ATP WINDOW 2026-12-28..2026-12-30 (ticker dates)" in out


def test_a_tour_whose_read_refused_has_no_window_counts(capsys):
    fake = provider(cursors={(("KXATPMATCH", "settled"), 0): "c1", (("KXATPMATCH", "settled"), 1): "c1"})
    code, out, _ = run(capsys, "--from", "2026-12-28", "--through", "2026-12-30", fake=fake)
    assert code == R.REFUSED, out
    assert "ATP WINDOW 2026-12-28..2026-12-30 (ticker dates): not counted (the tour's read did not answer)" in out
    assert list(_tail(out)["window"]["tours"]) == ["WTA"]


@pytest.mark.parametrize("args, says", [
    (["--from", "2026-12-31", "--through", "2026-12-30"], "--from 2026-12-31 is after --through 2026-12-30"),
    (["--from", "2026-13-01"], "REFUSED: --from '2026-13-01' is not a date YYYY-MM-DD"),
    (["--through", "20261230"], "REFUSED: --through '20261230' is not a date YYYY-MM-DD"),
    (["--from", "26DEC28"], "REFUSED: --from '26DEC28' is not a date YYYY-MM-DD"),
    (["--from", "2026-12-28T00:00"], "REFUSED: --from '2026-12-28T00:00' is not a date YYYY-MM-DD"),
    (["--from", ""], "REFUSED: --from '' is not a date YYYY-MM-DD"),
    (["--from", "2027-01-05"], "is after --through"),                  # a lone bound past the default's other bound
    (["--from", "2026-12-28", "--db", "copy.db"], "not with --db (the STORED phase)"),
])
def test_window_refusals_exit_2_before_any_call(tmp_path, capsys, monkeypatch, args, says):
    """309 item 6: a malformed date or --from after --through is REFUSED, exit 2, before any call; nothing written."""
    from datetime import date
    monkeypatch.setattr(R, "utc_today", lambda: date(2026, 12, 29))
    args = [str(tmp_path / a) if a == "copy.db" else a for a in args]
    before = set(tmp_path.rglob("*"))
    fake = provider()
    code, out, _ = run(capsys, *args, "--tickers", str(tmp_path / "d"), fake=fake)
    assert code == R.REFUSED, out
    assert says in out and "nothing read, nothing written" in out, out
    assert fake.calls == []
    assert set(tmp_path.rglob("*")) == before
    tail = _tail(out)
    assert tail["exit"] == R.REFUSED and "window" not in tail


def test_the_docs_name_the_window_line():
    doc = (ROOT / "docs" / "CLI.md").read_text()
    row = next(ln for ln in doc.splitlines() if ln.startswith("| `python3 scripts/tennis_certification_receipt.py` |"))
    assert "`[--from YYYY-MM-DD --through YYYY-MM-DD]`" in row and "addendum 309 item 6" in row
    assert "<TOUR> WINDOW <from>..<through> (ticker dates)" in row and "{yesterday}" in row
    assert "addendum 309 item 6" in R.__doc__ and "The comparison the first load needed (308 item 2" in R.__doc__
    # the comparison names the load's own range, not the 3-day default (the first load wrote seven ticker days)
    doc = " ".join(R.__doc__.split())
    assert "pass the load's own `sync-matches --date-from` / `--date-to`" in doc
    assert "`--from 2026-11-04 --through 2026-11-10`" in doc
    assert "the 3-day default does not match that load's stored counts" in doc
    assert "--from 2026-11-04 --through 2026-11-10" in row and "the load's own" in row
