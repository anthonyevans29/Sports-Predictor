"""THE CLOSE'S RECORD (ARCHITECT 2026-10-20 09:59 ET, addendum 146 item 5(b)), verbatim: "(b) results-tally gains
"the close's record" per market-only competition (NHL, NCAA, CL): games with a decided result and a last two-sided
Kalshi quote before kickoff (the kalshi_only close rule), the close's log-loss and the favourite's record, n. This is the
bar a college or cup candidate is scored against (roadmap: "no college candidate has been scored against a close")."

close.close_from_kalshi is called directly, after the mismatched-legs guard: books are never read. Each test runs on a
throwaway SQLite file (tests/test_record_vs_close.py iso_db); the Kalshi rows follow tests/test_book_source_times_615.py
(OddsSnapshot market ML, source kalshi, yes_bid / yes_ask). The three-way close (ARCHITECT 2026-10-20, addendum 150):
tests/test_close_record_three_way.py."""
import hashlib
import math
from datetime import datetime, timedelta

import pytest

from src.db.schema import MatchStatus, Sport
from src.walters import paper
from tests.test_record_vs_close import iso_db  # noqa: F401  (a fixture: a throwaway SQLite, cwd = tmp_path)

pytestmark = pytest.mark.usefixtures("iso_db")

NOW = datetime(2026, 10, 20, 14, 0)
KO = datetime(2026, 10, 18, 23, 0)
NONE = "no Kalshi close {k} (no two-sided quote before kickoff, or the last one over the 2c cap)"
TWO_KIND = "close: kalshi_only two-way"


def _comps():
    from src.db.database import session_scope
    from src.db.schema import Competition
    with session_scope() as s:
        for sport, code in ((Sport.NHL, "NHL"), (Sport.NFL, "NCAA"), (Sport.SOCCER, "CL")):
            s.add(Competition(sport=sport, code=code, name=code, area="X", type="LEAGUE"))


def _game(mid, code, hs, aw, ko=KO, status=MatchStatus.FINISHED, hs90=None, aw90=None, raw=None):
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, Team
    with session_scope() as s:
        c = s.query(Competition).filter_by(code=code).one()
        h, a = Team(sport=c.sport, name=f"H{mid}"), Team(sport=c.sport, name=f"A{mid}")
        s.add_all([h, a])
        s.flush()
        s.add(Match(id=mid, sport=c.sport, competition_id=c.id, season="2026", utc_date=ko, status=status,
                    home_team_id=h.id, away_team_id=a.id, home_score=hs, away_score=aw, home_score_90=hs90,
                    away_score_90=aw90, status_raw=raw))


def _kal(mid, sel, bid, ask, at, market="ML"):
    from src.db.database import session_scope
    from src.db.schema import OddsSnapshot
    with session_scope() as s:
        s.add(OddsSnapshot(match_id=mid, market=market, selection=sel, devig_prob=0.5, n_books=1, captured_at=at,
                           source="kalshi", yes_bid=bid, yes_ask=ask))


def _line(code, days=30):
    """The competition's two-way line, its close kind named (addendum 150 item 1: every line names its kind), returned
    as the built line read before the kind was named, so every number below is pinned unchanged."""
    rec = paper.close_record(days, now=NOW)
    x = next(x for x in paper.close_record_section(rec, days).splitlines() if x.startswith(f"- {code} · "))
    assert x.startswith(f"- {code} · {TWO_KIND} · "), x
    return f"- {code}: " + x[len(f"- {code} · {TWO_KIND} · "):]


def test_nhl_the_kalshi_mid_is_the_close_and_books_are_not_read():
    from src.db.database import session_scope
    from src.db.schema import Odds
    _comps()
    _game(501, "NHL", 4, 2)                                              # HOME wins
    _kal(501, "HOME", 0.60, 0.61, KO - timedelta(minutes=30))
    _kal(501, "AWAY", 0.39, 0.40, KO - timedelta(minutes=30))
    with session_scope() as s:                                           # a complete pre-kickoff book session
        for bk in ("bk1", "bk2"):
            for sel, px in (("HOME", 3.0), ("AWAY", 1.4)):
                s.add(Odds(match_id=501, bookmaker=bk, market="1X2", selection=sel, price_decimal=px,
                           captured_at=KO - timedelta(minutes=20)))
    _game(502, "NHL", 1, 3)                                              # AWAY wins
    _kal(502, "HOME", 0.44, 0.45, KO - timedelta(minutes=30))
    ll = (-math.log((0.60 + 0.61) / 2) - math.log(1 - (0.44 + 0.45) / 2)) / 2
    assert _line("NHL") == (f"- NHL: close log-loss {ll:.4f} · favourite 2/2 (100.0%) · n=2 · finished 2; left out: "
                            "none")
    assert f"{ll:.4f}" == "0.5457"


def test_an_upset_is_a_favourite_miss():
    _comps()
    _game(503, "NHL", 4, 2)
    _kal(503, "HOME", 0.60, 0.61, KO - timedelta(minutes=30))
    _game(504, "NHL", 2, 4)
    _kal(504, "HOME", 0.60, 0.61, KO - timedelta(minutes=30))           # the favourite (HOME) loses
    assert " · favourite 1/2 (50.0%) · n=2 · " in _line("NHL")


@pytest.mark.parametrize("quotes", [
    [(0.58, 0.61, 10), (0.60, 0.61, 60)],          # the last two-sided quote is 3c wide; the older 1c one is stale
    [(0.60, 0.61, -5)],                            # only quotes after the puck drop
    [(0.60, None, 30)],                            # bid only: not two-sided
], ids=["wide-last", "after-kickoff", "bid-only"])
def test_no_kalshi_close(quotes):
    _comps()
    _game(505, "NHL", 4, 2)
    for bid, ask, mins in quotes:
        _kal(505, "HOME", bid, ask, KO - timedelta(minutes=mins))
    assert _line("NHL") == ("- NHL: close log-loss — · favourite — · n=0 · finished 1; left out: "
                            + NONE.format(k=1))


def test_mismatched_legs_are_counted_and_never_priced():
    from sqlalchemy import text

    from src.db.database import session_scope
    _comps()
    _game(506, "NHL", 4, 2)
    _kal(506, "HOME", 0.60, 0.61, KO - timedelta(minutes=30))
    _kal(506, "AWAY", 0.39, 0.40, KO - timedelta(minutes=30))
    with session_scope() as s:                                           # what migrate_kalshi_ticker.py does
        s.execute(text("ALTER TABLE odds_snapshots ADD COLUMN market_ticker VARCHAR(64)"))
        s.execute(text("UPDATE odds_snapshots SET market_ticker = 'KXNHLGAME-26OCT18AAABBB-AAA' "
                       "WHERE selection = 'HOME'"))
        s.execute(text("UPDATE odds_snapshots SET market_ticker = 'KXNHLGAME-26OCT18CCCDDD-DDD' "
                       "WHERE selection = 'AWAY'"))
    assert _line("NHL") == "- NHL: close log-loss — · favourite — · n=0 · finished 1; left out: mismatched legs 1"


def test_no_decided_result_is_counted_before_mismatched_legs():
    """The order of exclusion (spec 3a): a level-scored game whose legs are also mismatched is "no decided result",
    never "mismatched legs"."""
    from sqlalchemy import text

    from src.db.database import session_scope
    _comps()
    _game(513, "NHL", 2, 2)
    _kal(513, "HOME", 0.60, 0.61, KO - timedelta(minutes=30))
    _kal(513, "AWAY", 0.39, 0.40, KO - timedelta(minutes=30))
    with session_scope() as s:
        s.execute(text("ALTER TABLE odds_snapshots ADD COLUMN market_ticker VARCHAR(64)"))
        s.execute(text("UPDATE odds_snapshots SET market_ticker = 'KXNHLGAME-26OCT18AAABBB-AAA' "
                       "WHERE selection = 'HOME'"))
        s.execute(text("UPDATE odds_snapshots SET market_ticker = 'KXNHLGAME-26OCT18CCCDDD-DDD' "
                       "WHERE selection = 'AWAY'"))
    assert _line("NHL") == "- NHL: close log-loss — · favourite — · n=0 · finished 1; left out: no decided result 1"


def test_a_level_or_null_score_is_no_decided_result():
    _comps()
    _game(507, "NHL", 2, 2)
    _game(508, "NHL", None, None)
    for mid in (507, 508):
        _kal(mid, "HOME", 0.60, 0.61, KO - timedelta(minutes=30))
    assert _line("NHL") == "- NHL: close log-loss — · favourite — · n=0 · finished 2; left out: no decided result 2"


def test_ncaa_reads_the_cfbd_label_first_and_a_tie_is_a_data_defect():
    from src.db.database import session_scope
    from src.db.schema import NCAACFBDLabel
    _comps()
    _game(601, "NCAA", 20, 17)                                           # the matches row: HOME
    with session_scope() as s:                                           # the label of record: AWAY 20-17
        s.add(NCAACFBDLabel(match_id=601, source="cfbd", source_game_id=1, season="2026", orientation="same",
                            home_score=17, away_score=20, fetched_at=NOW))
    _kal(601, "HOME", 0.30, 0.31, KO - timedelta(minutes=30))
    _game(602, "NCAA", 21, 21)                                           # no label: the matches row, level
    _kal(602, "HOME", 0.50, 0.51, KO - timedelta(minutes=30))
    ll = -math.log(1 - (0.30 + 0.31) / 2)
    assert _line("NCAA") == (f"- NCAA: close log-loss {ll:.4f} · favourite 1/1 (100.0%) · n=1 · finished 2; left out: "
                             "tie 1 (college football cannot tie: a data defect)")


def test_the_two_way_lines_name_their_close_kind_and_are_otherwise_unchanged():
    """Addendum 150 item 1: every line names its close kind; the NHL and NCAA lines keep the kalshi_only two-way close
    as built (the numbers of test_nhl_the_kalshi_mid_is_the_close_and_books_are_not_read, whole)."""
    _comps()
    _game(501, "NHL", 4, 2)
    _kal(501, "HOME", 0.60, 0.61, KO - timedelta(minutes=30))
    rec = paper.close_record(30, now=NOW)
    lines = paper.close_record_section(rec, 30).splitlines()
    assert f"- NHL · {TWO_KIND} · close log-loss {-math.log(0.605):.4f} · favourite 1/1 (100.0%) · n=1 · finished 1; " \
           "left out: none" in lines
    assert f"- NCAA · {TWO_KIND} · close log-loss — · favourite — · n=0 · finished 0; left out: none" in lines
    assert (rec["NHL"]["kind"], rec["NCAA"]["kind"], rec["CL"]["kind"]) == (
        "kalshi_only two-way", "kalshi_only two-way", "kalshi three-way (one capture, normalized)")


def test_an_even_close_counts_in_n_and_the_log_loss_never_in_the_record():
    _comps()
    _game(509, "NHL", 3, 1)
    _kal(509, "HOME", 0.49, 0.51, KO - timedelta(minutes=30))            # 2c: within the cap, mid exactly 0.50
    assert _line("NHL") == (f"- NHL: close log-loss {-math.log(0.5):.4f} · favourite — · n=1 (even 1) · finished 1; "
                            "left out: none")


def test_the_window_and_the_status():
    _comps()
    _game(510, "NHL", 4, 2, ko=NOW - timedelta(days=31))                 # older than --days 30
    _game(511, "NHL", None, None, ko=NOW + timedelta(hours=5), status=MatchStatus.SCHEDULED)
    _game(512, "NHL", 4, 2)
    for mid, ko in ((510, NOW - timedelta(days=31)), (512, KO)):
        _kal(mid, "HOME", 0.60, 0.61, ko - timedelta(minutes=30))
    rec = paper.close_record(30, now=NOW)
    assert (rec["NHL"]["finished"], rec["NHL"]["n"]) == (1, 1)
    assert paper.close_record(40, now=NOW)["NHL"]["n"] == 2


def test_a_game_exactly_the_window_old_is_in_it():
    """The window is inclusive at its edge (Match.utc_date >= now - days)."""
    _comps()
    edge = NOW - timedelta(days=30)
    _game(515, "NHL", 4, 2, ko=edge)
    _kal(515, "HOME", 0.60, 0.61, edge - timedelta(minutes=30))
    assert (paper.close_record(30, now=NOW)["NHL"]["finished"], paper.close_record(30, now=NOW)["NHL"]["n"]) == (1, 1)


def test_the_whole_section_and_the_console():
    _comps()
    rec = paper.close_record(30, now=NOW)
    assert paper.close_record_section(rec, 30) == (
        "## THE CLOSE'S RECORD — market-only, PAPER (ARCHITECT 2026-10-20, addendum 146 item 5(b); the three-way "
        "close, addendum 150)\n\n"
        "_The bar a college or cup candidate is scored against (roadmap: \"no college candidate has been scored against "
        "a close\"). Per competition, the FINISHED games of the last 30 days on the kickoff in this machine's DB that "
        "have a decided result and a close; every line names its close kind, and the two kinds never pool. close: "
        "kalshi_only two-way (NHL, NCAA): the mid of the last two-sided Kalshi HOME quote before kickoff within the 2c "
        "spread cap (src/walters/close.py close_from_kalshi); the favourite is the side the close prices above the "
        "other. close: kalshi three-way (one capture, normalized) (CL, and each other market-only three-way "
        "competition with a stored Kalshi 1X2 leg in the window; ARCHITECT 2026-10-20, addendum 150): the last capture "
        "before kickoff in which all three legs (HOME, DRAW, AWAY) are two-sided; a leg of it wider than the 2c cap "
        "leaves the game with no close (no older capture is substituted, legs of different captures are never "
        "combined); the three mids sum-normalized to 1 as the export forms the venue fair (export._summarize_kalshi), "
        "their raw sum the overround; scored on the 90-minute result (intl_shadow.result_90: 90 minutes plus "
        "stoppage, a knockout decided in extra time or on penalties is its 90-minute result); the favourite is the "
        "largest of the three, the draw included and flagged; a game left with no close is counted unpriced on its own "
        "line, by cause. Both: on a game whose Kalshi legs read as a set (addendum 37 item 3); books are not read; the "
        "close's log-loss is the mean of -ln(max(p, 1e-12)) of the outcome that happened; an exact tie at the top (a "
        "two-way close of exactly 0.50) has no favourite (it counts in n and the log-loss, not in the record). Never "
        "a call: nothing here enters the ledger, the P&L or a position._\n\n"
        "- NHL · close: kalshi_only two-way · close log-loss — · favourite — · n=0 · finished 0; left out: none\n"
        "- NCAA · close: kalshi_only two-way · close log-loss — · favourite — · n=0 · finished 0; left out: none\n"
        "- CL · close: kalshi three-way (one capture, normalized) · close log-loss — · favourite — · n=0 · finished 0; "
        "left out: none\n"
        "  - CL · close: kalshi three-way · unpriced 0: no capture before kickoff with all three legs two-sided 0; the "
        "last full capture has a leg over the 2c cap 0 (no older capture substituted)\n")
    assert paper.close_record_console(rec, 30) == ("the close's record (PAPER; 30 days): kalshi_only two-way: NHL n=0 · "
                                                   "NCAA n=0; kalshi three-way (one capture, normalized): CL n=0 "
                                                   "(unpriced 0)")


def test_results_tally_places_it_after_unl_before_the_footer_and_reports_it(tmp_path):
    from src.timeutil import utc_now_naive
    from src.walters.export import results_tally
    _comps()
    ko = utc_now_naive().replace(microsecond=0) - timedelta(days=2)
    _game(520, "NHL", 4, 2, ko=ko)
    _kal(520, "HOME", 0.60, 0.61, ko - timedelta(minutes=30))
    out, said = tmp_path / "RESULTS.md", []
    results_tally(days=30, out_path=str(out), report=said.append, exports_dir=str(tmp_path / "none"))
    txt = out.read_text()
    i_unl, i_rec, i_foot = (txt.index("## UNL — "), txt.index("## THE CLOSE'S RECORD — market-only, PAPER"),
                            txt.index("Deep detail: `BACKLOG.md`"))
    assert i_unl < i_rec < i_foot
    # addendum 150 item 1: the header names the grading close, so the PAPER record's three-way close is its own
    assert ("a three-way board never takes a Kalshi grading close (the PAPER record's three-way close, addendum 150, "
            "is its own)") in txt
    assert f"- NHL · {TWO_KIND} · close log-loss {-math.log(0.605):.4f} · favourite 1/1 (100.0%) · n=1 · finished 1" \
        in txt
    assert ("the close's record (PAPER; 30 days): kalshi_only two-way: NHL n=1 · NCAA n=0; kalshi three-way (one "
            "capture, normalized): CL n=0 (unpriced 0)") in said


def test_results_tally_scores_the_close_over_its_own_days(tmp_path):
    """results-tally --days 40: a game 35 days old is scored, and the console line names 40 days."""
    from src.timeutil import utc_now_naive
    from src.walters.export import results_tally
    _comps()
    ko = utc_now_naive().replace(microsecond=0) - timedelta(days=35)
    _game(521, "NHL", 4, 2, ko=ko)
    _kal(521, "HOME", 0.60, 0.61, ko - timedelta(minutes=30))
    out, said = tmp_path / "RESULTS.md", []
    results_tally(days=40, out_path=str(out), report=said.append, exports_dir=str(tmp_path / "none"))
    assert f"- NHL · {TWO_KIND} · close log-loss {-math.log(0.605):.4f} · favourite 1/1 (100.0%) · n=1 · finished 1" \
        in out.read_text()
    assert ("the close's record (PAPER; 40 days): kalshi_only two-way: NHL n=1 · NCAA n=0; kalshi three-way (one "
            "capture, normalized): CL n=0 (unpriced 0)") in said


def test_read_only_and_never_a_call(tmp_path):
    _comps()
    _game(530, "NHL", 4, 2)
    _kal(530, "HOME", 0.60, 0.61, KO - timedelta(minutes=30))
    _game(531, "CL", 1, 1)
    db = tmp_path / "iso.db"
    before = (hashlib.sha256(db.read_bytes()).hexdigest(), db.stat().st_mtime_ns)
    rec = paper.close_record(30, now=NOW)
    txt = paper.close_record_section(rec, 30)
    assert (hashlib.sha256(db.read_bytes()).hexdigest(), db.stat().st_mtime_ns) == before
    body = [x for x in txt.splitlines() if x.startswith("- ")]
    assert len(body) == 3
    for word in ("call", "units", "PLAY", "order"):
        assert not any(word in x for x in body), word
    for word in ("units", "PLAY", "order"):
        assert word not in txt, word
    assert txt.count("call") == 1 and "Never a call: nothing here enters the ledger" in txt
