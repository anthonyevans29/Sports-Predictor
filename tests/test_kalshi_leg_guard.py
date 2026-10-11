"""LEGS OF TWO EVENTS ARE NEVER A PAIR (ARCHITECT 2026-10-10, addendum 37 item 3, RULED): "A game's Kalshi legs are
read as a set only when their tickers name one event and that event's current legs sit on no other game. Otherwise
the row says mismatched and names the events, and nothing is computed from those legs: no price, no normalized
probability, no cost, no venue row, no line move, no close, no order line. Legs with no stored ticker are read as
before."

The world is the addendum 37 receipt A (laptop fixtures_NCAA_2026-10-10.json), with the names and tickers as the
receipt gives them (prefix KXNCAAFGAME-), moved to 2094 so no other test's rows meet them."""
import sqlite3
from collections import Counter
from datetime import datetime, timedelta

import pytest
from sqlalchemy import inspect, select, text

from src.db.database import get_engine, init_db, session_scope, write_kalshi_tickers
from src.db.schema import Competition, Match, MatchStatus, OddsSnapshot, Sport, Team
from src.walters import kalshi_legs as kl

P = "KXNCAAFGAME-94OCT10"
DAY = datetime(2094, 10, 10)
CAP = datetime(2094, 10, 10, 11, 52, 9)           # the receipt's capture time, before every kickoff below
# (match key, away, home, kickoff hour UTC, {side: (ticker suffix, bid, ask)})
GAMES = [
    ("32747", "Houston", "Kansas State", 19.5, {"HOME": ("KUUTAH-KU", .13, .14), "AWAY": ("HOUKSU-HOU", .45, .46)}),
    ("32810", "Florida A&M", "Alabama State", 20, {"HOME": ("UGAALA-ALA", .52, .53), "AWAY": ("FAMUALST-FAMU", .13, .14)}),
    ("32812", "North Dakota", "Northern Iowa", 21, {"HOME": ("UNDUNI-UNI", .17, .18), "AWAY": ("NDSUUNLV-NDSU", .59, .60)}),
    ("32772", "Coastal Carolina", "Marshall", 23, {"HOME": ("CCARMRSH-MRSH", .63, .64), "AWAY": ("SCSTCHSO-SCST", .67, .68)}),
    ("32738", "Georgia", "Alabama", 23.5, {"HOME": ("COOKAAMU-AAMU", .58, .59)}),
    ("32820", "North Dakota State", "UNLV", 23, {"HOME": ("NDSUUNLV-UNLV", .40, .41)}),
    ("32817", "South Carolina State", "Charleston Southern", 16, {"HOME": ("SCSTCHSO-CHSO", .31, .32),
                                                                   "AWAY": ("SCSTCHSO-SCST", .67, .68)}),
    ("32823", "Bethune-Cookman", "Alabama A&M", 17, {"AWAY": ("COOKAAMU-COOK", .41, .42)}),
    ("CLEAN", "Stanford", "Boston College", 19, {"HOME": ("STANBC-BC", .44, .46), "AWAY": ("STANBC-STAN", .54, .56)}),
    ("NOTIX", "Rice", "Tulane", 18, {"HOME": (None, .30, .31), "AWAY": (None, .69, .70)}),
]
RECEIPT_FIVE = ("32747", "32810", "32812", "32772", "32738")


def _ensure_ticker_column():
    eng = get_engine()
    if "market_ticker" not in {c["name"] for c in inspect(eng).get_columns("odds_snapshots")}:
        with eng.begin() as conn:                          # what migrate_kalshi_ticker.py does
            conn.execute(text("ALTER TABLE odds_snapshots ADD COLUMN market_ticker VARCHAR(64)"))


@pytest.fixture(scope="module")
def world():
    init_db()
    _ensure_ticker_column()
    ids = {}
    with session_scope() as s:
        comp = Competition(sport=Sport.NFL, code="KLGNCAA", name="KLG college", area="USA", type="LEAGUE")
        s.add(comp)
        s.flush()
        for key, away, home, hour, legs in GAMES:
            h, a = Team(sport=Sport.NFL, name=f"KLG {home}"), Team(sport=Sport.NFL, name=f"KLG {away}")
            s.add_all([h, a])
            s.flush()
            m = Match(sport=Sport.NFL, competition_id=comp.id, season="2094", status=MatchStatus.SCHEDULED,
                      utc_date=DAY + timedelta(hours=hour), home_team_id=h.id, away_team_id=a.id)
            s.add(m)
            s.flush()
            pairs = []
            for sel, (suffix, bid, ask) in legs.items():
                sn = OddsSnapshot(match_id=m.id, market="ML", selection=sel, devig_prob=(bid + ask) / 2, n_books=1,
                                  captured_at=CAP, source="kalshi", yes_bid=bid, yes_ask=ask)
                s.add(sn)
                pairs.append((sn, f"{P}{suffix}" if suffix else None))
            s.flush()
            write_kalshi_tickers(s, [(sn.id, t) for sn, t in pairs])
            ids[key] = m.id
    return ids


def test_event_of_is_the_ticker_without_its_last_segment():
    assert kl.event_of("KXNCAAFGAME-26OCT10NDSUUNLV-NDSU") == "KXNCAAFGAME-26OCT10NDSUUNLV"
    assert kl.event_of(None) is None and kl.event_of("NODASH") is None


def test_judge_is_pure_and_reads_untickered_legs_as_before():
    assert kl.judge({"HOME": "E1-H", "AWAY": "E1-A"}, {"E1": {7}}, 7) is None
    assert kl.judge({"HOME": "E1-H", "AWAY": "E2-A"}, {"E1": {7}, "E2": {7, 8}}, 7) == ["E1", "E2"]
    assert kl.judge({"HOME": "E1-H"}, {"E1": {7, 8}}, 7) == ["E1"]           # its event's legs sit on game 8
    assert kl.judge({"HOME": None, "AWAY": None}, {}, 7) is None
    assert kl.judge({"HOME": "E1-H", "AWAY": None}, {"E1": {7}}, 7) is None   # the untickered leg names no event


def test_the_receipts_five_rows_read_mismatched_and_the_clean_rows_do_not(world):
    with session_scope() as s:
        mm = kl.mismatched(s, list(world.values()))
    for k in RECEIPT_FIVE:
        assert world[k] in mm, k
    assert mm[world["32747"]] == [f"{P}HOUKSU", f"{P}KUUTAH"]
    assert mm[world["32812"]] == [f"{P}NDSUUNLV", f"{P}UNDUNI"]
    assert mm[world["32738"]] == [f"{P}COOKAAMU"]                             # one leg, its event also on 32823
    # the rule as ruled also reaches the true games whose event's legs sit on another game
    for k in ("32820", "32817", "32823"):
        assert world[k] in mm, k
    assert world["CLEAN"] not in mm and world["NOTIX"] not in mm


def test_fixtures_row_says_mismatched_names_the_events_and_carries_no_number(world):
    from src.walters.export import _fixture_row
    with session_scope() as s:
        for k in RECEIPT_FIVE:
            counts = Counter()
            r = _fixture_row(s, s.get(Match, world[k]), "KLGNCAA", Counter(), counts)
            assert r["kalshi"]["status"] == "mismatched" and r["kalshi"]["events"], k
            assert "prob" not in r["kalshi"] and "captured_at" not in r["kalshi"]
            assert r["kalshi_legs"] is None
            assert r["kalshi_bid"] is None and r["kalshi_ask"] is None and r["exec_cost_taker"] is None
            assert r["input_quality"]["kalshi"] == "mismatched" and counts["kalshi_mismatched"] == 1
        clean = _fixture_row(s, s.get(Match, world["CLEAN"]), "KLGNCAA", Counter(), Counter())
        notix = _fixture_row(s, s.get(Match, world["NOTIX"]), "KLGNCAA", Counter(), Counter())
    assert clean["kalshi"]["status"] == "two_sided" and clean["kalshi_bid"] == 0.44
    assert clean["kalshi_legs"]["HOME"]["ticker"] == f"{P}STANBC-BC"
    assert notix["kalshi"]["status"] == "two_sided" and notix["kalshi_legs"]["HOME"]["ticker"] is None


def test_no_venue_price_no_line_move_and_no_close_from_mismatched_legs(world, monkeypatch):
    from src.walters import close as close_mod
    from src.walters.kalshi_legs import guard_snaps
    from src.walters.line_move import line_move_for_match
    from src.walters.venue import kalshi_home_prob
    with session_scope() as s:
        for k in ("32812", "CLEAN"):
            m = s.get(Match, world[k])
            snaps = list(s.execute(select(OddsSnapshot).where(OddsSnapshot.match_id == m.id)).scalars())
            kept, evs = guard_snaps(snaps, s)
            if k == "CLEAN":
                assert evs is None and kalshi_home_prob(kept, m.utc_date) is not None
            else:
                assert kept == [] and evs and kalshi_home_prob(kept, m.utc_date) is None
                # line move: inside T-3h, the Kalshi venue has no series at all
                lm = line_move_for_match(s, m, m.utc_date - timedelta(hours=1))
                assert lm is None or "kalshi" not in lm["venues"]
        # grading close: with no book session, a mismatched game gets no Kalshi-only close; a clean one does
        m_bad, m_ok = s.get(Match, world["32747"]), s.get(Match, world["CLEAN"])
        assert close_mod.grading_close(s, m_bad) is None
        ok = close_mod.grading_close(s, m_ok)
        assert ok is not None and ok["source"] == "kalshi_only"


def test_the_closing_runs_capture_read_on_a_sqlite3_connection(world):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy" / "hosting"))
    import closing
    url = str(get_engine().url).replace("sqlite:///", "")
    con = sqlite3.connect(url)
    try:
        bad = closing.price_captures(con, world["32772"], DAY + timedelta(hours=23))
        ok = closing.price_captures(con, world["CLEAN"], DAY + timedelta(hours=19))
    finally:
        con.close()
    assert bad["kalshi"] is None and bad["kalshi_legs"] == {}
    assert ok["kalshi"] is not None and set(ok["kalshi_legs"]) == {"HOME", "AWAY"}


def test_before_the_ticker_migration_the_guard_answers_nothing(world, monkeypatch):
    monkeypatch.setattr(kl, "has_tickers", lambda conn: False)
    with session_scope() as s:
        assert kl.mismatched(s, list(world.values())) == {}


def test_nothing_stored_is_deleted_or_rewritten(world):
    with session_scope() as s:
        before = s.execute(select(OddsSnapshot.id, OddsSnapshot.devig_prob)
                           .where(OddsSnapshot.match_id.in_(list(world.values())))).all()
        kl.mismatched(s, list(world.values()))
        after = s.execute(select(OddsSnapshot.id, OddsSnapshot.devig_prob)
                          .where(OddsSnapshot.match_id.in_(list(world.values())))).all()
    assert sorted(before) == sorted(after) and len(before) == 17


def test_desk_meta_says_the_guard_is_on():
    from src.walters import desk_policy as dp
    doc = {"sport": "nfl", "predictions": []}
    dp.annotate(doc)
    assert doc["desk_meta"]["kalshi_leg_guard"] is True


def test_the_window_card_carries_no_kalshi_number_for_a_mismatched_row(world, tmp_path):
    from src.walters.window import build_card
    card = build_card(now=DAY + timedelta(hours=12), hours=12, export_dir=str(tmp_path))
    rows = {r["match_id"]: r for r in card["fixtures"]} if "fixtures" in card else \
        {r["match_id"]: r for r in card["rows"]}
    bad, ok = rows[world["32812"]], rows[world["CLEAN"]]
    assert bad["kalshi"]["status"] == "mismatched" and bad["kalshi_home_norm"] is None
    assert bad["venue_gap_pp"] is None and bad["kalshi_legs"] is None
    assert ok["kalshi_home_norm"] is not None
    assert card["receipts"]["kalshi_mismatched"] >= 5


def test_legs_tied_at_the_newest_capture_are_all_judged(world):
    """Codex on #414: two HOME legs of one game tie at the newest capture with different events; whichever a reader
    keeps, the game reads mismatched."""
    with session_scope() as s:
        m = s.get(Match, world["CLEAN"])
        mk = lambda: OddsSnapshot(match_id=m.id, market="ML", selection="HOME", devig_prob=.5, n_books=1,
                                  captured_at=CAP, source="kalshi", yes_bid=.49, yes_ask=.51)
        foreign, clean = mk(), mk()
        s.add(foreign)
        s.flush()
        s.add(clean)                       # the highest id is the clean leg: an id-only tie-break approves it
        s.flush()
        write_kalshi_tickers(s, [(foreign.id, f"{P}OTHER-BC"), (clean.id, f"{P}STANBC-BC")])
        try:
            assert kl.mismatched(s, [m.id]).get(m.id) == [f"{P}OTHER", f"{P}STANBC"]
        finally:
            s.delete(foreign)
            s.delete(clean)


def test_a_mismatched_block_is_not_a_shown_quote_nor_a_priced_row():
    """Codex on #414: closing.shows_kalshi and the window pager read the status block as carrying no price."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy" / "hosting"))
    import closing
    import sp_window_page
    block = kl.status_block([f"{P}A", f"{P}B"])
    assert closing.shows_kalshi({"market": {"kalshi": block}, "kalshi_legs": None}) is False
    assert closing.shows_kalshi({"market": {"kalshi": {"prob": {"HOME": .5}}}}) is True
    snap = sp_window_page.snapshot({"fixtures": [
        {"match_id": 1, "market": None, "kalshi": block},
        {"match_id": 2, "market": None, "kalshi": {"status": "two_sided", "prob": {"HOME": .5, "AWAY": .5}}}]})
    assert snap["1"]["priced"] is False and snap["2"]["priced"] is True
