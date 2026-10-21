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
        "competition with a stored Kalshi 1X2 leg in the window; ARCHITECT 2026-10-20, addendum 150; R42 ruled (b), "
        "addendum 151 item 1): the last capture before kickoff that holds any leg of the game, a close only when it "
        "holds all three legs (HOME, DRAW, AWAY) two-sided within the 2c cap (a later capture holding any leg ends the "
        "search; no older capture is substituted, legs of different captures are never combined); the three mids sum-normalized to 1 as the export forms the venue fair (export._summarize_kalshi), "
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
        "  - CL · close: kalshi three-way · unpriced 0: last capture incomplete 0 (a leg missing or one-sided; no older "
        "capture substituted); last capture over the cap 0 (no older capture substituted); no capture 0\n")
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


# ---- Codex round 2 P1 on #640 (R47): the HOME row the two-way close reads -------------------------------------------

E1 = {"HOME": "KXNHLGAME-26OCT18AAABBB-AAA", "AWAY": "KXNHLGAME-26OCT18AAABBB-BBB"}
E2 = {"HOME": "KXNHLGAME-26OCT18CCCDDD-CCC", "AWAY": "KXNHLGAME-26OCT18CCCDDD-DDD"}
OLD, NEW = KO - timedelta(hours=3), KO - timedelta(minutes=30)


def _tick(*legs):
    """What migrate_kalshi_ticker.py adds, then each (match, selection, captured_at, ticker or None) leg's
    market_ticker, one stored row each."""
    from sqlalchemy import text

    from src.db.database import session_scope
    with session_scope() as s:
        s.execute(text("ALTER TABLE odds_snapshots ADD COLUMN market_ticker VARCHAR(64)"))
        for mid, sel, at, tic in legs:
            n = s.execute(text("UPDATE odds_snapshots SET market_ticker = :v WHERE match_id = :m AND selection = :s "
                               "AND substr(captured_at, 1, 19) = :t"),
                          {"v": tic, "m": mid, "s": sel, "t": at.strftime("%Y-%m-%d %H:%M:%S")}).rowcount
            assert n == 1, (mid, sel, at, n)


def _codex_game(mid, old_home_ticker, old=(0.60, 0.61)):
    """Codex's case on NHL `mid` (HOME wins): the newest HOME leg one-sided (no bid) and the newest AWAY leg, both of
    event AAABBB at KO-30m; an older two-sided HOME quote at KO-3h whose ticker is `old_home_ticker`."""
    _game(mid, "NHL", 4, 2)
    _kal(mid, "HOME", old[0], old[1], OLD)
    _kal(mid, "HOME", None, 0.50, NEW)
    _kal(mid, "AWAY", 0.39, 0.40, NEW)
    return [(mid, "HOME", OLD, old_home_ticker), (mid, "HOME", NEW, E1["HOME"]), (mid, "AWAY", NEW, E1["AWAY"])]


def _verdict(mid):
    """paper.close_row_mismatched on the game's stored rows, as close_record judges them."""
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Match, OddsSnapshot
    with session_scope() as s:
        m = s.get(Match, mid)
        snaps = {mid: list(s.execute(select(OddsSnapshot).where(OddsSnapshot.match_id == mid)).scalars())}
        tickers, current, homes = paper.two_way_legs(s, [m], snaps)
        read = paper.kalshi_close_read(snaps[mid], m.utc_date)
        return ([x.captured_at for x in read], paper.close_row_mismatched(read, tickers, current.get(mid), mid, homes),
                {x.id: tickers.get(x.id) for x in read})


def test_the_row_the_two_way_close_reads_of_another_games_event_is_mismatched():
    """Codex round 2 P1 on #640 (R47): NHL 701's newest legs (HOME one-sided, AWAY) are all of event AAABBB, so the
    ruled guard (kalshi_legs.mismatched) passes; close_from_kalshi falls back to the older two-sided HOME quote, of
    event CCCDDD, whose current legs sit on NHL 702. Before the fix 701 was priced from 702's contract (n=2, mismatched
    0); now the row the close reads is judged with each side's newest leg: "mismatched legs", no close, and 702 is
    priced from its own legs."""
    from src.db.database import session_scope
    from src.walters import kalshi_legs
    _comps()
    legs = _codex_game(701, E2["HOME"])
    _game(702, "NHL", 1, 3)                                              # AWAY wins
    _kal(702, "HOME", 0.44, 0.45, NEW)
    _kal(702, "AWAY", 0.55, 0.56, NEW)
    _tick(*legs, (702, "HOME", NEW, E2["HOME"]), (702, "AWAY", NEW, E2["AWAY"]))
    with session_scope() as s:
        assert kalshi_legs.mismatched(s, [701, 702]) == {}              # each side's newest leg: the guard passes
    assert _verdict(701)[:2] == ([OLD], ["KXNHLGAME-26OCT18AAABBB", "KXNHLGAME-26OCT18CCCDDD"])
    assert _verdict(702)[1] is None
    assert _line("NHL") == (f"- NHL: close log-loss {-math.log(1 - 0.445):.4f} · favourite 1/1 (100.0%) · n=1 · "
                            "finished 2; left out: mismatched legs 1")


def test_the_row_read_of_an_event_on_no_game_is_mismatched_with_the_newest_legs():
    """The union with each side's newest leg (kalshi_legs.judge, its first clause): the older two-sided HOME quote is of
    event EEEFFF, whose current legs sit on no game, while 701's newest legs are all of AAABBB: two events, so
    "mismatched legs" (judged alone, the row would read as a set)."""
    _comps()
    _tick(*_codex_game(701, "KXNHLGAME-26OCT18EEEFFF-EEE"))
    assert _verdict(701)[1] == ["KXNHLGAME-26OCT18AAABBB", "KXNHLGAME-26OCT18EEEFFF"]
    assert _line("NHL") == "- NHL: close log-loss — · favourite — · n=0 · finished 1; left out: mismatched legs 1"


def test_a_normal_game_is_still_priced_from_the_older_two_sided_quote():
    """The same shape with every leg of event AAABBB: the row read (KO-3h) and the newest legs read as a set, so the
    close is close_from_kalshi's, unchanged (the older two-sided quote's mid 0.605)."""
    _comps()
    _tick(*_codex_game(701, E1["HOME"]))
    assert _verdict(701)[:2] == ([OLD], None)
    assert _line("NHL") == (f"- NHL: close log-loss {-math.log(0.605):.4f} · favourite 1/1 (100.0%) · n=1 · finished 1; "
                            "left out: none")


def test_an_untickered_row_read_names_no_event():
    """kalshi_legs: "Legs with no stored ticker are read as before": the older two-sided HOME row has no stored ticker
    (NULL), so it names no event; the newest legs (AAABBB) read as a set and the game is priced. Before
    migrate_kalshi_ticker.py (no ticker column) two_way_legs reads nothing and every row is untickered."""
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Match, OddsSnapshot
    _comps()
    _game(703, "NHL", 4, 2)
    _kal(703, "HOME", 0.60, 0.61, OLD)
    with session_scope() as s:                                           # no ticker column yet
        m = s.get(Match, 703)
        snaps = {703: list(s.execute(select(OddsSnapshot).where(OddsSnapshot.match_id == 703)).scalars())}
        assert paper.two_way_legs(s, [m], snaps) == ({}, {}, {})
    assert " · n=1 · " in _line("NHL")
    _tick(*_codex_game(701, None))
    when, verdict, tickers = _verdict(701)
    assert (when, verdict, list(tickers.values())) == ([OLD], None, [None])
    assert paper.close_row_mismatched([type("Row", (), {"id": 1})()], {}, {"HOME": {E1["HOME"]}}, 701,
                                      {"KXNHLGAME-26OCT18AAABBB": {701}}) is None
    assert _line("NHL") == (f"- NHL: close log-loss {-math.log(0.605):.4f} · favourite 2/2 (100.0%) · n=2 · finished 2; "
                            "left out: none")


def test_the_row_read_is_judged_before_its_cap():
    """The order of exclusion on the row read: mismatched legs before no Kalshi close. The older two-sided HOME quote
    of another event is 3c wide (close_from_kalshi gives no close): "mismatched legs", never "no Kalshi close" (nothing
    is judged from legs of two events, addendum 37 item 3; as _score_three judges its capture before its cap)."""
    _comps()
    _tick(*_codex_game(701, E2["HOME"], old=(0.58, 0.61)))
    assert _line("NHL") == "- NHL: close log-loss — · favourite — · n=0 · finished 1; left out: mismatched legs 1"


@pytest.mark.parametrize("scheduled", [False, True], ids=["the-other-game-finished", "the-other-game-scheduled"])
def test_the_row_read_of_an_event_whose_current_legs_sit_on_another_game_is_mismatched(scheduled):
    """The ruled guard's second clause on the row the two-way close reads (addendum 37 item 3: "that event's current
    legs sit on no other game"; the verifier on Codex round 2, #640): 701's newest legs carry no ticker (they name no
    event), and its older two-sided HOME row is of event CCCDDD, whose current legs sit on 702. 701 is "mismatched
    legs", never priced from 702's contract, whether 702 is finished (scored itself) or still scheduled a day later
    (outside the record's games: the event's homes are read over the row read, not over the games scored)."""
    _comps()
    legs = _codex_game(701, E2["HOME"])
    if scheduled:
        _game(702, "NHL", None, None, ko=KO + timedelta(days=1), status=MatchStatus.SCHEDULED)
    else:
        _game(702, "NHL", 1, 3)
    _kal(702, "HOME", 0.44, 0.45, NEW)
    _kal(702, "AWAY", 0.55, 0.56, NEW)
    _tick(legs[0], (701, "HOME", NEW, None), (701, "AWAY", NEW, None),
          (702, "HOME", NEW, E2["HOME"]), (702, "AWAY", NEW, E2["AWAY"]))
    r = paper.close_record(30, now=NOW)["NHL"]
    assert (r["n"], r["mismatched"]) == ((0, 1) if scheduled else (1, 1))


def test_rows_tied_at_the_capture_read_are_all_judged():
    """Two two-sided HOME rows at the capture read, of two events: whichever close_from_kalshi keeps, both are judged
    (as kalshi_legs judges legs tied at one capture, Codex on #414), so the game is mismatched in either row order."""
    from types import SimpleNamespace as R
    rows = [R(id=1, source="kalshi", market="ML", selection="HOME", captured_at=OLD, yes_bid=0.60, yes_ask=0.61),
            R(id=2, source="kalshi", market="ML", selection="HOME", captured_at=OLD, yes_bid=0.50, yes_ask=0.51)]
    tickers = {1: E1["HOME"], 2: E2["HOME"]}
    for order in (rows, rows[::-1]):
        read = paper.kalshi_close_read(order, KO)
        assert read[0] is paper.kalshi_close_row(order, KO) and {x.id for x in read} == {1, 2}
        assert paper.close_row_mismatched(read, tickers, {"AWAY": {E1["AWAY"]}}, 701, {}) == [
            "KXNHLGAME-26OCT18AAABBB", "KXNHLGAME-26OCT18CCCDDD"]
    assert paper.kalshi_close_read([], KO) == [] and paper.close_row_mismatched([], tickers, {}, 701, {}) is None


def test_the_helper_and_close_from_kalshi_agree_on_the_same_rows():
    """kalshi_close_row is the exact row close.close_from_kalshi reads (close.py unchanged): over a seeded battery of
    stored-row shapes (sources, markets, selections, missing or tied capture times, one-sided, crossed and wide
    quotes, cutoffs), whenever the close is priced its capture time, bid and ask are that row's; when the helper reads
    no row there is no close; when it reads one and there is no close, that row fails the bounds or the 2c cap."""
    import random
    from types import SimpleNamespace as R

    from src.walters import close as cl
    from src.walters.desk_policy import KALSHI_ONLY, js_round
    rnd = random.Random(640)
    times = [KO - timedelta(minutes=m) for m in (240, 120, 30, 30, 5)] + [KO + timedelta(minutes=10), None]
    quotes = [(0.60, 0.61), (0.50, 0.52), (0.40, 0.43), (None, 0.55), (0.55, None), (0.62, 0.60), (0.0, 0.0),
              (0.99, 1.0), (0.30, 0.31)]
    seen = {"priced": 0, "none_read": 0, "fails": 0, "tied_priced": 0}
    for i in range(3000):
        rows = []
        for j in range(rnd.randint(0, 7)):
            bid, ask = rnd.choice(quotes)
            rows.append(R(id=j, source=rnd.choice(["kalshi", "kalshi", "kalshi", "odds_api"]),
                          market=rnd.choice(["ML", "ML", "1X2", "SPREAD"]), selection=rnd.choice(["HOME", "HOME",
                                                                                                  "AWAY", "DRAW"]),
                          captured_at=rnd.choice(times), yes_bid=bid, yes_ask=ask))
        before = rnd.choice([KO, KO, None, KO - timedelta(minutes=60)])
        got, k = cl.close_from_kalshi(rows, before, cl.BINARY), paper.kalshi_close_row(rows, before)
        if k is None:
            assert got is None, i
            seen["none_read"] += 1
        elif got is not None:
            assert (got["captured_at"], got["kalshi"]["bid"], got["kalshi"]["ask"]) == (
                k.captured_at, float(k.yes_bid), float(k.yes_ask)), i
            seen["priced"] += 1
            seen["tied_priced"] += len(paper.kalshi_close_read(rows, before)) > 1 and len(
                {(x.yes_bid, x.yes_ask) for x in paper.kalshi_close_read(rows, before)}) > 1
        else:
            bid, ask = float(k.yes_bid), float(k.yes_ask)
            assert (not (0.0 <= bid <= ask <= 1.0) or ask <= 0.0 or bid >= 1.0
                    or js_round((ask - bid) * 100) > KALSHI_ONLY["maxSpreadC"]), i
            seen["fails"] += 1
    assert min(seen.values()) > 0, seen                    # every branch met, ties of different quotes among the priced
