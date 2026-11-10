"""THE TENNIS WIRING, the Kalshi and host half (ARCHITECT 2026-11-05, addendum 261 items 0 and 2(c); 2026-11-06,
addendum 269 item 3(a), (e), (f), addendum 274 item 1(b); 2026-11-07, addendum 284 item 1(b); lane tennis-market-only,
#838).

The two series on the venue's maps and their fee M (1.0, 1.0) read from the schedule (274 item 1(b)); the capture:
the shared matcher's placement, then tennis's player check on yes_sub_title (a market naming neither player, or both,
REFUSED by its sentinel, never guessed); `sync-kalshi-atp` / `sync-kalshi-wta`; the hourly capture tier; the PAPER
line and coverage; the close's record decided by Kalshi's settlement (a SETTLED_SCALAR row never scored); the chain
tennis-daily and its timer, shipped not enabled.

Every market, ticker and player name here is SYNTHETIC. The throwaway DBs only; no network (the HTTP layer is a
fake)."""
from __future__ import annotations

import math
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from click.testing import CliRunner

ROOT = Path(__file__).resolve().parent.parent
HOSTING = ROOT / "deploy" / "hosting"
sys.path.insert(0, str(HOSTING))

import chains  # noqa: E402

from src.adapters import kalshi_tennis as kt  # noqa: E402
from src.ingestion import kalshi_match as km  # noqa: E402
from src.ingestion import tennis_kalshi as tk  # noqa: E402
from src.walters import venue  # noqa: E402
from tests import test_coverage_map as tcm  # noqa: E402
from tests.test_coverage_map import env  # noqa: E402,F401  (a fixture)
from tests.test_record_vs_close import iso_db  # noqa: E402,F401  (a fixture)
from tests.test_tennis_wiring import FakeKalshi, OPEN, _fake_http, pair, tennis_rows  # noqa: E402,F401

Z = datetime.fromisoformat


# ---- the series and the fee M ------------------------------------------------------------------------------------------

def test_the_two_series_are_mapped_and_priced_at_the_m_read_from_the_schedule():
    """274 item 1(b) (as the roadmap's tennis lane and #838 record it): "KXATPMATCH and KXWTAMATCH (1.0, 1.0), read
    from the schedule". Tennis rows price both costs, both sides, at M = 1, exactly as NBA's; no other entry moved."""
    from src.ingestion.kalshi_replay import shared_series
    from src.ingestion.kalshi_sync import series_competition
    assert venue.KALSHI_SERIES_BY_COMPETITION["ATP"] == "KXATPMATCH"
    assert venue.KALSHI_SERIES_BY_COMPETITION["WTA"] == "KXWTAMATCH"
    assert venue.KALSHI_FEE_M["KXATPMATCH"] == venue.KALSHI_FEE_M["KXWTAMATCH"] == (1.0, 1.0)
    assert series_competition("KXATPMATCH") == "ATP" and shared_series()["KXWTAMATCH"] == "WTA"
    assert venue.KALSHI_FEE_M == {"KXNFLGAME": (1.0, 1.0), "KXNHLGAME": (1.0, 1.0), "KXNCAAFGAME": (1.0, 1.0),
                                  "KXEPLGAME": (1.0, 1.0), "KXMLBGAME": (0.5, 0.5), "KXUCLGAME": (1.0, 1.0),
                                  "KXNBAGAME": (1.0, 1.0), "KXATPMATCH": (1.0, 1.0), "KXWTAMATCH": (1.0, 1.0)}
    src = (ROOT / "src" / "walters" / "venue.py").read_text()
    blk = src[src.index("# KXATPMATCH and KXWTAMATCH"):src.index('"KXATPMATCH": (1.0, 1.0)')]
    assert "addendum 274 item 1(b)" in blk and "read" in blk and "from the schedule" in blk
    costs = ("exec_cost_taker", "exec_cost_maker", "exec_cost_taker_away", "exec_cost_maker_away")
    nba = venue.kalshi_exec(0.53, 0.55, "NBA", two_way=True)
    for code, series in (("ATP", "KXATPMATCH"), ("WTA", "KXWTAMATCH")):
        e = venue.kalshi_exec(0.53, 0.55, code, two_way=True)
        assert (e["fee_series"], e["fee_m_taker"], e["fee_m_maker"]) == (series, 1.0, 1.0)
        assert [e[k] for k in costs] == [nba[k] for k in costs] and all(e[k] is not None for k in costs)


def test_the_k_track_reads_a_tennis_home_away_ladder_as_complete():
    from src.walters.k_receipt import ladder_row
    t = Z("2026-12-28T05:00")
    legs = {"HOME": NS(yes_bid=0.55, yes_ask=0.57), "AWAY": NS(yes_bid=0.43, yes_ask=0.45)}
    for comp in ("ATP", "WTA"):
        r = ladder_row(comp, t, legs, [], [])
        assert (r["complete"], r["two_sided"]) == (True, True), (comp, r)
        assert all(v["taker"] is not None and v["maker"] is not None for v in r["legs"].values()), r


def test_no_tennis_call_exists_to_price():
    """261 item 4: no model, no call, no Desk family."""
    from src.walters import desk_policy
    fams = repr(getattr(desk_policy, "FAMILIES", "")) + repr(getattr(desk_policy, "DESK_FAMILIES", ""))
    assert "ATP" not in fams and "WTA" not in fams and "tennis" not in fams.lower()
    from src.walters import training
    assert not [k for k in training.MODEL_FAMILIES if "tennis" in str(k).lower()]


# ---- the player check (269 item 3(a)) ----------------------------------------------------------------------------------

def _row(mid, home, away, event):
    return NS(id=mid, home_team=NS(name=home), away_team=NS(name=away), external_ids={kt.SOURCE: event})


def _placed(*items):
    res = km.Result()
    for (mid, side), name, event in items:
        res.placed[(mid, side)] = {"ticker": f"{event}-{name[:3].upper()}", "event_ticker": event, "yes_sub_title": name}
    return res


E1 = "KXATPMATCH-26DEC29AAABBB"


@pytest.mark.parametrize("side,name,event,rows,why", [
    ("HOME", "Ana Synthwood", E1, [_row(1, "Ana Synthwood", "Bea Fakely", E1)], None),
    ("AWAY", "bea fakely", E1, [_row(1, "Ana Synthwood", "Bea Fakely", E1)], None),            # letter case only
    ("HOME", "Cal Mockton", E1, [_row(1, "Ana Synthwood", "Bea Fakely", E1)], tk.PLAYER_NEITHER),
    ("HOME", "Ana Synthwood", E1, [_row(1, "Ana Synthwood", "Ana Synthwood", E1)], tk.PLAYER_BOTH),
    ("AWAY", "Ana Synthwood", E1, [_row(1, "Ana Synthwood", "Bea Fakely", E1)], tk.PLAYER_SIDE),
    ("HOME", "Ana Synthwood", E1, [_row(1, "Ana Synthwood", "Bea Fakely", "KXATPMATCH-26DEC28CCCDDD")],
     tk.EVENT_OTHER),
    ("HOME", "Ana Synthwood", E1, [], tk.EVENT_OTHER),
])
def test_the_player_check_keeps_only_the_named_player_on_their_own_event_and_side(side, name, event, rows, why):
    res = tk.player_check(_placed(((1, side), name, event)), rows)
    if why is None:
        assert list(res.placed) == [(1, side)] and not res.refused
    else:
        assert res.placed == {} and res.refused == {why: 1} and why in res.why.values()


def test_a_refused_market_is_counted_in_the_unmatched_never_stored():
    res = tk.player_check(_placed(((1, "HOME"), "Cal Mockton", E1)), [_row(1, "Ana Synthwood", "Bea Fakely", E1)])
    c = km.legacy_counts(res)
    assert c["matched"] == 0 and c["unmatched"] == 1 and c["refused"] == {tk.PLAYER_NEITHER: 1}


# ---- sync-kalshi-atp end to end ----------------------------------------------------------------------------------------

def test_sync_kalshi_atp_refuses_without_the_competition(monkeypatch, tennis_rows):
    import cli
    fake = FakeKalshi({("KXATPMATCH", "open"): [OPEN]})
    _fake_http(monkeypatch, fake)
    out = CliRunner().invoke(cli.cli, ["sync-kalshi-atp"])
    assert out.exit_code == 0 and "✗ Kalshi ATP: competition ATP not in DB" in out.output, out.output
    assert {p["series_ticker"] for path, p in fake.calls if path == "markets"} == {"KXATPMATCH"}


def test_sync_kalshi_atp_refuses_a_cursor_left_and_stores_nothing(monkeypatch, tennis_rows):
    import cli
    fake = FakeKalshi({("KXATPMATCH", "open"): [OPEN, OPEN]},
                      cursors={(("KXATPMATCH", "open"), 0): "c1", (("KXATPMATCH", "open"), 1): "c1"})
    _fake_http(monkeypatch, fake)
    out = CliRunner().invoke(cli.cli, ["sync-kalshi-atp"])
    flat = " ".join(out.output.split())
    assert out.exit_code == 0 and "✗ Kalshi ATP: REFUSED" in flat and "cursor already read" in flat, flat


OCC = kt.OCCURRENCE_KEY
# the stage-1 digest's open event, its served start a SYNTHETIC 14:00Z on its ticker's date (+14 h, inside 288 item 1's
# +7 h to +29 h)
OPEN_T = pair("26DEC29EEEFFF", "Eli Sampleton", "Ana Synthwood", times={OCC: "2026-12-29T14:00:00Z"})


def _synced(monkeypatch, pages, lo="2026-12-28", hi="2026-12-30"):
    import cli
    fake = FakeKalshi(pages)
    _fake_http(monkeypatch, fake)
    run = CliRunner()
    assert run.invoke(cli.cli, ["sync-competitions", "--sport", "tennis"]).exit_code == 0
    res = run.invoke(cli.cli, ["sync-matches", "--competition", "ATP", "--date-from", lo, "--date-to", hi])
    assert res.exit_code == 0, res.output
    return fake, run


def _tennis_snaps():
    from src.db.database import session_scope
    from src.db.schema import Match, OddsSnapshot, Sport
    with session_scope() as s:
        return s.query(OddsSnapshot).join(Match, Match.id == OddsSnapshot.match_id).filter(
            Match.sport == Sport.TENNIS).count()


def test_sync_kalshi_atp_stores_both_players_on_the_ml_market(monkeypatch, tennis_rows):
    """The event's own row (created from the same event by sync-matches), both players placed on their sides by the
    shared matcher and kept by the player check and the kickoff check; an event with no stored row is refused by the
    shared matcher's NO_FIT, counted and printed; a WTA market is never read by the ATP sync."""
    import cli
    from src.db.database import session_scope
    from src.db.schema import Match, OddsSnapshot
    fake, run = _synced(monkeypatch, {("KXATPMATCH", "open"): [OPEN_T]})
    monkeypatch.setattr(tk, "utc_now_naive", lambda: Z("2026-12-28T05:00"))
    fake.pages[("KXATPMATCH", "open")] = [OPEN_T + pair("26DEC29GGGHHH", "Nowhere Person", "Elsewhere Person")]
    out = run.invoke(cli.cli, ["sync-kalshi-atp"])
    assert out.exit_code == 0, out.output
    assert "✓ Kalshi ATP: 2 prices stored" in out.output and "series KXATPMATCH · 4 markets" in out.output, out.output
    assert km.NO_FIT in out.output
    with session_scope() as s:
        m = next(x for x in s.query(Match).all()
                 if (x.external_ids or {}).get("kalshi_tennis") == "KXATPMATCH-26DEC29EEEFFF")
        assert (m.home_team.name, m.away_team.name) == ("Ana Synthwood", "Eli Sampleton")
        snaps = {x.selection: (x.market, x.source, x.yes_bid, x.yes_ask)
                 for x in s.query(OddsSnapshot).filter(OddsSnapshot.match_id == m.id)}
    assert snaps == {"HOME": ("ML", "kalshi", 0.40, 0.42), "AWAY": ("ML", "kalshi", 0.40, 0.42)}
    # in play at the real start (the served occurrence_datetime, 288 item 1): nothing more is stored
    monkeypatch.setattr(tk, "utc_now_naive", lambda: Z("2026-12-29T14:00"))
    out = run.invoke(cli.cli, ["sync-kalshi-atp"])
    assert "✓ Kalshi ATP: 0 prices stored" in out.output and km.IN_PLAY in out.output, out.output


def test_a_d_event_open_on_d_minus_1_afternoon_is_captured_ahead_of_its_served_start(monkeypatch, tennis_rows):
    """ARCHITECT 2026-11-08, addendum 288 item 1 (RULED, replacing the conservative rule #868 pinned here): the stored
    kickoff is the event's served occurrence_datetime, so a market of an event dated D still open at D-1 15:12 UTC (the
    stage-1 digest's KXWTAMATCH-26NOV07... open at ~15:12Z on 11-06) is captured, its kickoff ahead; IN_PLAY fires at
    the real start, a minute before it still captured."""
    import cli
    fake, run = _synced(monkeypatch, {("KXATPMATCH", "open"): [OPEN_T]})
    for now, stored in (("2026-12-28T15:12", 2), ("2026-12-29T13:59", 2), ("2026-12-29T14:00", 0)):
        monkeypatch.setattr(tk, "utc_now_naive", lambda now=now: Z(now))
        out = run.invoke(cli.cli, ["sync-kalshi-atp"])
        assert f"✓ Kalshi ATP: {stored} prices stored" in out.output, (now, out.output)
        assert (km.IN_PLAY in out.output) == (stored == 0), (now, out.output)


def test_a_start_unread_row_is_never_captured(monkeypatch, tennis_rows):
    """288 item 1: "absent on all four → the row is stored with the conservative UTC+14 instant AND the label
    START_UNREAD, so it is never captured". The row's stored kickoff source (external_ids['kalshi_kickoff']) is
    START_UNREAD: the shared matcher places the market (its UTC+14 instant still ahead, inside the run's window) and
    the kickoff check refuses it, counted and printed; nothing is stored. A row with no stored source at all (written
    before this rule) is refused too."""
    import cli
    from src.db.database import session_scope
    from src.db.schema import Match
    fake, run = _synced(monkeypatch, {("KXATPMATCH", "open"): [OPEN]})     # OPEN serves no time key
    with session_scope() as s:
        (m,) = [x for x in s.query(Match).all() if (x.external_ids or {}).get(kt.SOURCE)]
        assert (m.external_ids or {}).get(kt.KICKOFF_EXT_KEY) == kt.START_UNREAD
        assert m.utc_date == kt.kickoff_utc(datetime(2026, 12, 29).date())
    monkeypatch.setattr(tk, "utc_now_naive", lambda: Z("2026-12-28T05:00"))   # before the UTC+14 instant
    out = run.invoke(cli.cli, ["sync-kalshi-atp"])
    flat = " ".join(out.output.split())
    assert "✓ Kalshi ATP: 0 prices stored" in flat and tk.START_UNREAD_ROW in flat and km.IN_PLAY not in flat, flat
    # ARCHITECT 2026-11-08, addendum 294 item 9: a START_UNREAD row is not "due", so a run whose every placement the
    # kickoff rule refused does not raise the zero-placement alarm; one line counts the kickoff rule's refusals
    assert "MATCHED ZERO" not in flat and "matcher may be broken" not in flat, flat
    assert ("kickoff rule refused 2 placement(s) (addendum 294 item 9: a row whose stored kickoff source is not a "
            "served key is not due for the zero-placement alarm)") in flat, flat
    assert _tennis_snaps() == 0
    with session_scope() as s:                                          # a row stored before the rule: no source
        (m,) = [x for x in s.query(Match).all() if (x.external_ids or {}).get(kt.SOURCE)]
        m.external_ids = {k: v for k, v in (m.external_ids or {}).items() if k != kt.KICKOFF_EXT_KEY}
    out = run.invoke(cli.cli, ["sync-kalshi-atp"])
    flat = " ".join(out.output.split())
    assert "✓ Kalshi ATP: 0 prices stored" in flat and tk.KICKOFF_SOURCE_MISSING in flat, flat
    assert "MATCHED ZERO" not in flat and "kickoff rule refused 2 placement(s)" in flat, flat     # 294 item 9
    assert _tennis_snaps() == 0


def _now_served(kind):
    """OPEN_T's event as the venue might serve it after the row was stored (14:00Z, occurrence_datetime): `kind` is a
    kickoff-rule refusal of 288 item 1 (differ, one market, unread), no start served at all, or a moved start."""
    ev = pair("26DEC29EEEFFF", "Eli Sampleton", "Ana Synthwood", times={OCC: "2026-12-29T14:00:00Z"})
    if kind == "differ":
        ev[0][OCC] = "2026-12-29T10:00:00Z"
    elif kind == "one":
        del ev[0][OCC]
    elif kind == "unread":
        ev[0][OCC] = ev[1][OCC] = "2026-12-29 14:00"            # no zone: not read (law 4)
    elif kind == "none":
        del ev[0][OCC], ev[1][OCC]
    elif kind == "earlier":
        ev[0][OCC] = ev[1][OCC] = "2026-12-29T10:00:00Z"
    elif kind == "later":
        ev[0][OCC] = ev[1][OCC] = "2026-12-29T19:30:00Z"
    return ev


@pytest.mark.parametrize("kind,label", [
    ("differ", kt.OCCURRENCE_DIFFER),
    ("one", kt.OCCURRENCE_ONE_MARKET),
    ("unread", kt.OCCURRENCE_UNREAD),
])
def test_a_stored_row_whose_event_the_kickoff_rule_now_refuses_is_labelled_and_never_captured(monkeypatch, tennis_rows,
                                                                                             kind, label):
    """288 item 1: "a difference refuses the event with its own label, counted". ARCHITECT 2026-11-08, addendum 294
    item 13, verbatim: "a sync that refuses an event the row holds writes the refusal label into
    external_ids["kalshi_kickoff"] and nothing else (status, winner and receipt stay — law 4), counted". The row was
    stored from a served start (occurrence_datetime, 14:00Z); the venue now serves the event in a way the rule refuses.
    sync-matches refuses the event (no fixture) and writes the refusal label on the stored row, nothing else (its
    utc_date, status, status_raw, winner and settlement receipt stay), counted with the match id. The capture's kickoff
    check then refuses the row (its stored source is a refusal label, not a served key: KICKOFF_REFUSED_ROW), counted
    and printed with the label; the zero-placement alarm does not count the row as due (294 item 9). When the venue
    serves the event readably again, the next sync rewrites the source and the row is captured."""
    import cli
    from src.db.database import session_scope
    from src.db.schema import Match
    fake, run = _synced(monkeypatch, {("KXATPMATCH", "open"): [OPEN_T]})

    def row():
        with session_scope() as s:
            (m,) = [x for x in s.query(Match).all() if (x.external_ids or {}).get(kt.SOURCE)]
            return m.id, (m.utc_date, m.status.name, m.status_raw, m.full_time_result,
                          {k: v for k, v in (m.external_ids or {}).items() if k != kt.KICKOFF_EXT_KEY}), \
                (m.external_ids or {}).get(kt.KICKOFF_EXT_KEY)
    mid, kept, src = row()
    assert src == OCC and kept[0] == Z("2026-12-29T14:00")
    fake.pages[("KXATPMATCH", "open")] = [_now_served(kind)]
    res = run.invoke(cli.cli, ["sync-matches", "--competition", "ATP", "--date-from", "2026-12-28",
                               "--date-to", "2026-12-30"])
    assert res.exit_code == 0, res.output
    flat = " ".join(res.output.split())
    assert (f"ATP refused events held by stored rows (dated 2026-12-21..2026-12-30; the refusal label written to "
            f"external_ids['kalshi_kickoff'], nothing else on the row; addendum 294 item 13(b)): 1 · match {mid} "
            f"(KXATPMATCH-26DEC29EEEFFF: {label})") in flat, flat
    assert row() == (mid, kept, label)                     # the label written, and NOTHING else on the row
    monkeypatch.setattr(tk, "utc_now_naive", lambda: Z("2026-12-29T09:00"))
    out = run.invoke(cli.cli, ["sync-kalshi-atp"])
    flat = " ".join(out.output.split())
    assert "✓ Kalshi ATP: 0 prices stored" in flat and tk.KICKOFF_REFUSED_ROW in flat and label in flat, flat
    assert "MATCHED ZERO" not in flat, flat                                     # 294 item 9: the row is not due
    assert "kickoff rule refused 2 placement(s)" in flat, flat
    assert _tennis_snaps() == 0
    # the venue serves the event readably again: the next sync rewrites the source; the row is captured
    fake.pages[("KXATPMATCH", "open")] = [OPEN_T]
    res = run.invoke(cli.cli, ["sync-matches", "--competition", "ATP", "--date-from", "2026-12-28",
                               "--date-to", "2026-12-30"])
    assert res.exit_code == 0, res.output
    assert "ATP refused events held by stored rows" in res.output and row()[2] == OCC
    out = run.invoke(cli.cli, ["sync-kalshi-atp"])
    assert "✓ Kalshi ATP: 2 prices stored" in out.output, out.output


def test_a_settled_row_whose_event_the_rule_now_refuses_keeps_its_status_winner_and_receipt(monkeypatch, tennis_rows):
    """294 item 13 ("nothing else (status, winner and receipt stay — law 4)"; option (c), returning the row to
    SCHEDULED, is REFUSED by the ruling): a FINISHED row whose event the venue now serves with two different
    occurrence_datetime instants keeps its status, status_raw, winner, settlement receipt and utc_date; only its
    kickoff source becomes the refusal label. Inside the window and by the late re-read's lookback alike; a refused
    event of the same day that no stored row holds writes nothing (no new row)."""
    import cli
    from src.db.database import session_scope
    from src.db.schema import Match
    fin = dict(results=("yes", "no"), exps=("Eli Sampleton", "Eli Sampleton"), status="finalized",
               values=("1.0000", "0.0000"))
    ev = pair("26DEC29EEEFFF", "Eli Sampleton", "Ana Synthwood", times={OCC: "2026-12-29T14:00:00Z"}, **fin)
    fake, run = _synced(monkeypatch, {("KXATPMATCH", "settled"): [ev]})

    def rows():
        with session_scope() as s:
            return {(x.external_ids or {}).get(kt.SOURCE): (x.id, x.utc_date, x.status.name, x.status_raw,
                                                           getattr(x.full_time_result, "name", None),
                                                           dict(x.external_ids or {}))
                    for x in s.query(Match).all() if (x.external_ids or {}).get(kt.SOURCE)}
    (before,) = rows().values()
    assert before[2:5] == ("FINISHED", "finalized", "AWAY") and before[5].get("kalshi_settlement")
    bad = pair("26DEC29EEEFFF", "Eli Sampleton", "Ana Synthwood", times={OCC: "2026-12-29T14:00:00Z"}, **fin)
    bad[0][OCC] = "2026-12-29T18:00:00Z"
    other = pair("26DEC29TTTUUU", "Tia Unstored", "Ugo Unstored", times={OCC: "2026-12-29T15:00:00Z"}, **fin)
    other[0][OCC] = "2026-12-29T19:00:00Z"
    fake.pages = {("KXATPMATCH", "settled"): [bad + other]}
    for lo, hi in (("2026-12-28", "2026-12-30"), ("2027-01-01", "2027-01-03")):      # the window, then the lookback
        res = run.invoke(cli.cli, ["sync-matches", "--competition", "ATP", "--date-from", lo, "--date-to", hi])
        assert res.exit_code == 0, res.output
        assert f"1 · match {before[0]} (KXATPMATCH-26DEC29EEEFFF: {kt.OCCURRENCE_DIFFER})" in " ".join(
            res.output.split()), res.output
        got = rows()
        assert set(got) == {"KXATPMATCH-26DEC29EEEFFF"}                              # no new row
        (after,) = got.values()
        assert after[:5] == before[:5]                                                # status, winner, utc_date stay
        assert after[5] == {**before[5], kt.KICKOFF_EXT_KEY: kt.OCCURRENCE_DIFFER}    # the label and nothing else
    # beyond the lookback: the row is not touched, and the receipt counts none
    res = run.invoke(cli.cli, ["sync-matches", "--competition", "ATP", "--date-from", "2027-01-10",
                               "--date-to", "2027-01-12"])
    assert res.exit_code == 0 and "nothing else on the row; addendum 294 item 13(b)): 0" in " ".join(
        res.output.split()), res.output


# ---- THE VENUE-WIDE LINE (ARCHITECT 2026-11-08, addendum 297 item B.11) ----------------------------------------------
# "when the held rows labelled this run equal every held row in reach (and reach > 0), print "EVERY held row refused
# this run — the venue's serving changed" on the sync receipt (a line, not a page)"

def _sync(run, lo, hi):
    import cli
    res = run.invoke(cli.cli, ["sync-matches", "--competition", "ATP", "--date-from", lo, "--date-to", hi])
    assert res.exit_code == 0, res.output
    return res.output


def test_every_held_row_refused_with_reach_prints_the_venue_wide_line(monkeypatch, tennis_rows):
    """Two stored rows in reach, the venue now serving both events in a way the kickoff rule refuses: both labelled,
    so the line prints once, after the count; the exit stays 0 (a line, not a page)."""
    import cli
    two = OPEN_T + pair("26DEC30GGGHHH", "Gus Oldfield", "Hal Pastly", times={OCC: "2026-12-30T15:00:00Z"})
    fake, run = _synced(monkeypatch, {("KXATPMATCH", "open"): [two]})
    bad = _now_served("differ") + pair("26DEC30GGGHHH", "Gus Oldfield", "Hal Pastly",
                                       times={OCC: "2026-12-30T15:00:00Z"})
    bad[2][OCC] = "2026-12-30T19:00:00Z"
    fake.pages[("KXATPMATCH", "open")] = [bad]
    out = _sync(run, "2026-12-28", "2026-12-30")
    flat = " ".join(out.split())
    assert "addendum 294 item 13(b)): 2 · match" in flat, flat
    assert cli.EVERY_HELD_REFUSED == "EVERY held row refused this run — the venue's serving changed"
    assert out.count(f"  ATP {cli.EVERY_HELD_REFUSED}\n") == 1, out
    assert flat.index("addendum 294 item 13(b)): 2") < flat.index(cli.EVERY_HELD_REFUSED)


def test_some_held_rows_refused_does_not_print_the_venue_wide_line(monkeypatch, tennis_rows):
    """One of two held rows in reach refused (the other served readably): the count reads 1 and the line is absent."""
    import cli
    two = OPEN_T + pair("26DEC30GGGHHH", "Gus Oldfield", "Hal Pastly", times={OCC: "2026-12-30T15:00:00Z"})
    fake, run = _synced(monkeypatch, {("KXATPMATCH", "open"): [two]})
    fake.pages[("KXATPMATCH", "open")] = [_now_served("differ") + two[2:]]
    out = _sync(run, "2026-12-28", "2026-12-30")
    assert "addendum 294 item 13(b)): 1 · match" in " ".join(out.split()), out
    assert cli.EVERY_HELD_REFUSED not in out, out


def test_no_held_row_in_reach_does_not_print_the_venue_wide_line(monkeypatch, tennis_rows):
    """reach 0: with no stored row in reach, 0 labelled equals 0 held, and the line stays absent (reach > 0 is part of
    the ruling). Two ways: a refused event no row holds and no row stored at all; a held row beyond the reach."""
    import cli
    fake = FakeKalshi({("KXATPMATCH", "open"): [_now_served("differ")]})
    _fake_http(monkeypatch, fake)
    run = CliRunner()
    assert run.invoke(cli.cli, ["sync-competitions", "--sport", "tennis"]).exit_code == 0
    out = _sync(run, "2026-12-28", "2026-12-30")
    assert "addendum 294 item 13(b)): 0" in " ".join(out.split()) and cli.EVERY_HELD_REFUSED not in out, out
    fake.pages[("KXATPMATCH", "open")] = [OPEN_T]
    _sync(run, "2026-12-28", "2026-12-30")                                   # the row is stored, then out of reach
    fake.pages[("KXATPMATCH", "open")] = [_now_served("differ")]
    out = _sync(run, "2027-01-10", "2027-01-12")
    assert "addendum 294 item 13(b)): 0" in " ".join(out.split()) and cli.EVERY_HELD_REFUSED not in out, out


@pytest.mark.parametrize("kind,at", [("earlier", "2026-12-29T11:00"), ("later", "2026-12-29T13:00")])
def test_a_start_moved_since_the_rows_sync_is_never_captured_until_a_sync_re_reads_it(monkeypatch, tennis_rows, kind,
                                                                                      at):
    """288 item 1: "the IN_PLAY refusal fires at the real start" and "the row follows it". The row was stored at 14:00Z;
    the venue now serves the start moved on both markets, and no sync has re-read the row (a manual capture, or a sync
    step that failed while the window chain went on). The capture never prices against the stale stored kickoff: it
    refuses (KICKOFF_MOVED, counted, the two instants printed; law 4), an hour past the earlier start or the hour
    before the stored one. After a sync re-reads the row, the row follows the served start and the shared matcher's
    IN_PLAY reads it (earlier: in play; later: captured)."""
    import cli
    fake, run = _synced(monkeypatch, {("KXATPMATCH", "open"): [OPEN_T]})
    fake.pages[("KXATPMATCH", "open")] = [_now_served(kind)]
    monkeypatch.setattr(tk, "utc_now_naive", lambda: Z(at))
    out = run.invoke(cli.cli, ["sync-kalshi-atp"])
    flat = " ".join(out.output.split())
    assert "✓ Kalshi ATP: 0 prices stored" in flat and tk.KICKOFF_MOVED in flat, flat
    assert "2026-12-29 14:00Z" in flat, flat                          # the stored instant, printed beside the served
    assert _tennis_snaps() == 0
    res = run.invoke(cli.cli, ["sync-matches", "--competition", "ATP", "--date-from", "2026-12-28",
                               "--date-to", "2026-12-30"])
    assert res.exit_code == 0, res.output
    out = run.invoke(cli.cli, ["sync-kalshi-atp"])
    flat = " ".join(out.output.split())
    assert tk.KICKOFF_MOVED not in flat, flat
    if kind == "earlier":
        assert "✓ Kalshi ATP: 0 prices stored" in flat and km.IN_PLAY in flat, flat
        assert _tennis_snaps() == 0
    else:
        assert "✓ Kalshi ATP: 2 prices stored" in flat, flat


def test_a_start_no_longer_served_is_never_captured_before_or_after_the_sync_re_reads_it(monkeypatch, tennis_rows):
    """288 item 1: "absent on all four → the row is stored with the conservative UTC+14 instant AND the label
    START_UNREAD, so it is never captured". The row was stored from a served start; the venue now serves no time key.
    Before a sync re-reads the row, the capture reads it off the markets it holds (KICKOFF_UNREAD_NOW); after the sync,
    the row follows (START_UNREAD, the UTC+14 instant) and the stored-source check refuses it (START_UNREAD_ROW)."""
    import cli
    from src.db.database import session_scope
    from src.db.schema import Match
    fake, run = _synced(monkeypatch, {("KXATPMATCH", "open"): [OPEN_T]})
    fake.pages[("KXATPMATCH", "open")] = [_now_served("none")]
    monkeypatch.setattr(tk, "utc_now_naive", lambda: Z("2026-12-28T05:00"))
    out = run.invoke(cli.cli, ["sync-kalshi-atp"])
    flat = " ".join(out.output.split())
    assert "✓ Kalshi ATP: 0 prices stored" in flat and tk.KICKOFF_UNREAD_NOW in flat, flat
    res = run.invoke(cli.cli, ["sync-matches", "--competition", "ATP", "--date-from", "2026-12-28",
                               "--date-to", "2026-12-30"])
    assert res.exit_code == 0, res.output
    with session_scope() as s:
        (m,) = [x for x in s.query(Match).all() if (x.external_ids or {}).get(kt.SOURCE)]
        assert (m.external_ids or {}).get(kt.KICKOFF_EXT_KEY) == kt.START_UNREAD
    out = run.invoke(cli.cli, ["sync-kalshi-atp"])
    flat = " ".join(out.output.split())
    assert "✓ Kalshi ATP: 0 prices stored" in flat and tk.START_UNREAD_ROW in flat, flat
    assert _tennis_snaps() == 0


def test_an_accepted_event_with_a_stray_market_outside_the_series_keeps_its_served_key_and_is_captured(
        monkeypatch, tennis_rows):
    """tennis-D review (finding: 13(b) labelled an ACCEPTED event). kalshi_tennis.build() refuses a market whose
    event_ticker is in the series but whose ticker is not (OUTSIDE_SERIES, keyed by its event ticker) and still accepts
    the event from its two markets in the series. 294 item 13(b) labels "a sync that refuses an event the row holds";
    this listing ACCEPTED the event, so its row keeps its served kickoff source (no label written, counted 0), and a
    capture the venue serves cleanly prices it (before the fix the label made the capture refuse it as
    KICKOFF_REFUSED_ROW). A capture that still reads the stray market refuses by the shared matcher's own ambiguity and
    the served kickoff check, as built in #877 (not this rule)."""
    import cli
    stray = dict(OPEN_T[0], ticker="KXOTHER-26DEC29EEEFFF-ZZZ")
    assert stray["event_ticker"] == "KXATPMATCH-26DEC29EEEFFF"
    fake, run = _synced(monkeypatch, {("KXATPMATCH", "open"): [OPEN_T + [stray]]})
    from src.db.database import session_scope
    from src.db.schema import Match
    res = run.invoke(cli.cli, ["sync-matches", "--competition", "ATP", "--date-from", "2026-12-28",
                               "--date-to", "2026-12-30"])
    assert res.exit_code == 0, res.output
    flat = " ".join(res.output.split())
    assert "1 events accepted · refused {'a ticker outside the series': 1}" in flat, flat
    assert "nothing else on the row; addendum 294 item 13(b)): 0" in flat, flat
    with session_scope() as s:
        (m,) = [x for x in s.query(Match).all() if (x.external_ids or {}).get(kt.SOURCE)]
        assert (m.external_ids or {}).get(kt.KICKOFF_EXT_KEY) == OCC
    fake.pages[("KXATPMATCH", "open")] = [OPEN_T]                          # the venue serves the event cleanly
    monkeypatch.setattr(tk, "utc_now_naive", lambda: Z("2026-12-29T09:00"))
    out = run.invoke(cli.cli, ["sync-kalshi-atp"])
    assert "✓ Kalshi ATP: 2 prices stored" in out.output, out.output
    assert tk.KICKOFF_REFUSED_ROW not in " ".join(out.output.split())


ALARM_TEXT = ("  ⚠ MATCHED ZERO with {n} markets read and {d} unstarted game(s) of the competition inside the run's "
              "window — matcher may be broken (see 2026-09-13 title-format incident). Probe the payload before "
              "trusting 'absent'.")


def test_a_tennis_row_read_from_a_served_key_still_alarms_when_nothing_is_placed(monkeypatch, tennis_rows):
    """294 item 9 for the tennis caller ONLY rows whose stored source is not a served key: a row stored from a served
    start whose placements the served kickoff check refuses (KICKOFF_MOVED: its stored source IS a served key) is still
    due, and a run that places nothing still raises the alarm, its text unchanged (an OPEN ITEM, as ruled)."""
    import cli
    fake, run = _synced(monkeypatch, {("KXATPMATCH", "open"): [OPEN_T]})
    fake.pages[("KXATPMATCH", "open")] = [_now_served("later")]
    monkeypatch.setattr(tk, "utc_now_naive", lambda: Z("2026-12-29T09:00"))
    out = run.invoke(cli.cli, ["sync-kalshi-atp"])
    flat = " ".join(out.output.split())
    assert tk.KICKOFF_MOVED in flat and "kickoff rule refused 2 placement(s)" in flat, flat
    assert " ".join(ALARM_TEXT.format(n=2, d=1).split()) in flat, flat


def test_the_shared_alarm_is_unchanged_for_every_other_series():
    """294 item 9: "the alarm's text and the shared code's behaviour for the other series unchanged". The shared
    _alarm, called as every other caller calls it (no `is_due`), counts every unstarted game in the window, whatever its
    external_ids carry (a START_UNREAD or refusal label on a non-tennis row is not read), and prints the same text; the
    tennis predicate is applied only when a caller passes it."""
    from src.ingestion import kalshi_sync as ks
    from src.db.schema import MatchStatus

    class Sess:
        def __init__(self, rows):
            self.rows = rows

        def execute(self, q):
            return NS(scalars=lambda: list(self.rows))
    now, lo, hi = Z("2026-12-28T05:00"), Z("2026-12-27T05:00"), Z("2026-12-30T05:00")
    rows = [NS(id=1, status=MatchStatus.SCHEDULED, utc_date=Z("2026-12-29T00:00"),
               external_ids={"kalshi_kickoff": kt.START_UNREAD}),
            NS(id=2, status=MatchStatus.SCHEDULED, utc_date=Z("2026-12-29T01:00"),
               external_ids={"kalshi_kickoff": kt.OCCURRENCE_DIFFER}),
            NS(id=3, status=MatchStatus.SCHEDULED, utc_date=Z("2026-12-29T02:00"), external_ids={})]
    mks = [{"ticker": "KXNFLGAME-26DEC28AABB-AA"}, {"ticker": "KXNFLGAME-26DEC28AABB-BB"}]
    lines = []
    assert ks._alarm(Sess(rows), [7], km.Result(), mks, now, lo, hi, lines.append) is True
    assert lines == [ALARM_TEXT.format(n=2, d=3)]
    # the tennis caller's predicate: only the row with a served key would count; none here, so no alarm
    lines = []
    assert ks._alarm(Sess(rows), [7], km.Result(), mks, now, lo, hi, lines.append, is_due=tk.due_for_alarm) is False
    assert lines == []
    rows[2].external_ids = {"kalshi_kickoff": kt.OCCURRENCE_KEY}
    assert ks._alarm(Sess(rows), [7], km.Result(), mks, now, lo, hi, lines.append, is_due=tk.due_for_alarm) is True
    assert lines == [ALARM_TEXT.format(n=2, d=1)]


def test_the_served_kickoff_check_needs_both_of_the_events_markets_in_hand():
    """The ruling reads the kickoff on BOTH markets of the event ("both markets of the event must carry the same
    value"); a capture holding one market of the event cannot read it, so the placement is refused (law 4; an OPEN
    ITEM), never read off the one market."""
    row = _row(1, "Ana Synthwood", "Bea Fakely", E1)
    row.utc_date = Z("2026-12-29T14:00")
    both = pair("26DEC29AAABBB", "Ana Synthwood", "Bea Fakely", times={OCC: "2026-12-29T14:00:00Z"})
    res = _placed(((1, "HOME"), "Ana Synthwood", E1))
    res.placed[(1, "HOME")] = both[0]
    kept = tk.served_kickoff_check(res, [row], both)
    assert list(kept.placed) == [(1, "HOME")] and not kept.refused
    res = _placed(((1, "HOME"), "Ana Synthwood", E1))
    res.placed[(1, "HOME")] = both[0]
    got = tk.served_kickoff_check(res, [row], both[:1])
    assert got.placed == {} and got.refused == {tk.KICKOFF_HELD_NOT_TWO: 1}


@pytest.mark.parametrize("src,why", [(kt.START_UNREAD, tk.START_UNREAD_ROW), (None, tk.KICKOFF_SOURCE_MISSING),
                                     ("something else", tk.START_UNREAD_ROW), (kt.OCCURRENCE_KEY, None),
                                     (kt.EXPIRATION_KEY, None)]
                         # 294 item 13(b): a row whose stored source is a refusal label (the sync refused its event)
                         + [(lab, "REFUSED_ROW") for lab in (
                             kt.OCCURRENCE_DIFFER, kt.EXPIRATION_DIFFER, kt.OCCURRENCE_ONE_MARKET,
                             kt.EXPIRATION_ONE_MARKET, kt.OCCURRENCE_UNREAD, kt.EXPIRATION_UNREAD, kt.NO_DATE,
                             kt.NOT_TWO_MARKETS, kt.NOT_TWO_PLAYERS, kt.OUTSIDE_SERIES)])
def test_the_kickoff_check_keeps_only_a_row_whose_kickoff_was_read_from_a_served_key(src, why):
    if why == "REFUSED_ROW":
        assert src in kt.REFUSAL_LABELS
        why = tk.KICKOFF_REFUSED_ROW
    row = _row(1, "Ana Synthwood", "Bea Fakely", E1)
    if src is not None:
        row.external_ids[kt.KICKOFF_EXT_KEY] = src
    res = tk.kickoff_check(_placed(((1, "HOME"), "Ana Synthwood", E1)), [row])
    if why is None:
        assert list(res.placed) == [(1, "HOME")] and not res.refused
    else:
        assert res.placed == {} and res.refused == {why: 1}


def test_a_same_pair_row_dated_the_day_after_no_longer_takes_the_days_market(monkeypatch, tennis_rows):
    """#868's REVIEW NIT, RESOLVED by the ruling (288 item 1: "the shared matcher's date-only rule therefore reads the
    right row"): with the served kickoffs, the D event's row reads on its own US Eastern day, so the date-only rule
    places the D event's markets on the D row, never on the same pair's D+1 row."""
    import cli
    from src.db.database import session_scope
    from src.db.schema import Match, OddsSnapshot
    d29 = pair("26DEC29AAABBB", "Ana Synthwood", "Bea Fakely", times={OCC: "2026-12-29T14:00:00Z"})
    d30 = pair("26DEC30CCCDDD", "Ana Synthwood", "Bea Fakely", times={OCC: "2026-12-30T14:00:00Z"})
    fake, run = _synced(monkeypatch, {("KXATPMATCH", "open"): [d29 + d30]})
    fake.pages[("KXATPMATCH", "open")] = [d29]
    monkeypatch.setattr(tk, "utc_now_naive", lambda: Z("2026-12-28T11:00"))
    out = run.invoke(cli.cli, ["sync-kalshi-atp"])
    flat = " ".join(out.output.split())
    assert "✓ Kalshi ATP: 2 prices stored" in flat and tk.EVENT_OTHER not in flat, flat
    with session_scope() as s:
        got = {(x.external_ids or {}).get(kt.SOURCE): s.query(OddsSnapshot).filter(OddsSnapshot.match_id == x.id).count()
               for x in s.query(Match).all() if (x.external_ids or {}).get(kt.SOURCE)}
    assert got == {"KXATPMATCH-26DEC29AAABBB": 2, "KXATPMATCH-26DEC30CCCDDD": 0}


# ---- the ruled offset range, the coverage day and the matcher's date-only rule (288 item 1) ---------------------------
# "occurrence_datetime [...] sits +7 h to +29 h after 00:00 UTC of the ticker's date — the ticker's date is the
# US-Eastern calendar day of the start (02:00–24:00 ET)". THE BOUNDARY, determined here (a FINDING put to the
# architect, the rule unchanged): US Eastern's day D is [05:00Z D, 05:00Z D+1) in EST and [04:00Z D, 04:00Z D+1) in
# EDT, so +29 h (EST) and +28 h / +29 h (EDT) fall on the US Eastern day D+1: "24:00 ET" is 00:00 of D+1 by the
# calendar. There the coverage page reads the row on D+1, not the ticker's date; the shared matcher's date-only rule
# still places the event's markets on the row (a game a day either side is on the event's day, and the one row of the
# pair is chosen), unless the same pair holds another row within a day of D (then the event is refused DATE_TIE, never
# placed on the other row).

EST_D, EDT_D = datetime(2026, 12, 29), datetime(2026, 7, 15)
ET_OFFSET_CASES = ([(EST_D, h, h < 29) for h in (7, 12, 19, 24, 28, 29)]      # (the day, +h, on the ticker's ET day)
                   + [(EDT_D, h, h < 28) for h in (7, 12, 24, 27, 28, 29)])


def _game(gid, ko, home="Ana Synthwood", away="Bea Fakely"):
    return NS(id=gid, utc_date=ko, home_team=NS(name=home), away_team=NS(name=away), home_team_id=1, away_team_id=2,
              status="scheduled")


def _mkts(day: datetime, ev="AAABBB"):
    stamp = day.strftime("%y%b%d").upper()
    return pair(f"{stamp}{ev}", "Ana Synthwood", "Bea Fakely")


@pytest.mark.parametrize("day,h,on_day", ET_OFFSET_CASES)
def test_the_coverage_day_is_the_tickers_date_inside_the_offset_range_and_the_next_day_at_its_edge(day, h, on_day):
    import coverage_map as cm
    from datetime import timezone
    ko = day + timedelta(hours=h)
    lo, hi = cm.day_bounds(day.date())
    nlo, nhi = cm.day_bounds(day.date() + timedelta(days=1))
    aware = ko.replace(tzinfo=timezone.utc)
    assert (lo <= aware < hi) == on_day and (nlo <= aware < nhi) == (not on_day), (ko, lo, hi)
    assert (km.et_day(ko) == day.date()) == on_day


@pytest.mark.parametrize("day,h,on_day", ET_OFFSET_CASES)
def test_the_matchers_date_only_rule_places_the_one_row_and_in_play_fires_at_the_real_start(day, h, on_day):
    ko = day + timedelta(hours=h)
    g = _game(7, ko)
    lo, hi = ko - timedelta(days=2), ko + timedelta(days=2)
    res = km.place(_mkts(day), [g], now=ko - timedelta(minutes=1), lo=lo, hi=hi)
    assert set(res.placed) == {(7, "HOME"), (7, "AWAY")} and not res.refused, (h, res.refused)
    res = km.place(_mkts(day), [g], now=ko, lo=lo, hi=hi)
    assert res.placed == {} and res.refused == {km.IN_PLAY: 2}


@pytest.mark.parametrize("day,h,on_day", ET_OFFSET_CASES)
def test_at_the_edge_a_same_pair_row_of_the_next_day_refuses_the_event_never_misplaces_it(day, h, on_day):
    """The D event's row at +h, and the same pair's D+1 event's row at +14 h on D+1. Inside the range each event takes
    its own row; at the edge (both rows on US Eastern day D+1) the D event is refused DATE_TIE and the D+1 event
    TWO_ROWS: never a market on the other event's row."""
    d_row, n_row = _game(7, day + timedelta(hours=h)), _game(8, day + timedelta(days=1, hours=14))
    now = day - timedelta(days=1)
    lo, hi = now, now + timedelta(days=5)
    res = km.place(_mkts(day) + _mkts(day + timedelta(days=1), "CCCDDD"), [d_row, n_row], now=now, lo=lo, hi=hi)
    if on_day:
        assert set(res.placed) == {(7, "HOME"), (7, "AWAY"), (8, "HOME"), (8, "AWAY")}, res.refused
        ev_d = next(k for k in res.placed if k[0] == 7)
        assert res.placed[ev_d]["event_ticker"].endswith(day.strftime("%y%b%d").upper() + "AAABBB")
    else:
        assert res.placed == {} and res.refused == {km.DATE_TIE: 2, km.TWO_ROWS: 2}, res.refused


@pytest.mark.parametrize("series", ["KXATPMATCH", "KXWTAMATCH"])
def test_the_settled_market_history_pull_refuses_the_tennis_series_before_any_call(series, monkeypatch):
    """Review P2: the venue map now names the two tour series, which would open `kalshi-history --series` (the
    settled-market history pull) for them. That pull is the ONE-TIME backfill addendum 270 item 5 holds for the
    architect's block, and it places with the shared matcher without tennis's player check (269 item 3(a)): REFUSED
    before any call, by the CLI's pull, the ruled re-place (place-held) and the anchored chain (place-chain)."""
    import inspect

    import cli
    from src.ingestion import kalshi_history as kh
    called = []
    monkeypatch.setattr(kh, "competition_for", lambda *a, **k: called.append(a) or ("ATP", False))
    with pytest.raises(ValueError, match="addendum 270 item 5"):
        kh.run_history(series, adapter=FakeKalshi(), echo=lambda *_: None, dry_run=True)
    with pytest.raises(ValueError, match="addendum 270 item 5"):
        kh._ruled_target(None, {"ticker": f"{series}-26DEC29AAABBB-AAA", "series": series}, 1, None)
    assert called == []
    src = inspect.getsource(kh._plan_chain)
    assert src.index("refuse_held_series(series)") < src.index("competition_for(series, adapter)")
    kh.refuse_held_series("KXNBAGAME")                       # every other series passes unchanged
    res = CliRunner().invoke(cli.cli, ["kalshi-history", "--series", series, "--dry-run"])
    assert res.exit_code == 2 and "addendum 270 item 5" in " ".join(res.output.split()), res.output


# ---- the chain, the capture tier, the timer ----------------------------------------------------------------------------

def test_tennis_daily_is_both_tours_window_then_their_kalshi_syncs():
    ch = chains.CHAINS["tennis-daily"]
    assert ch["steps"] == [
        ["sync-matches", "--competition", "ATP", "--date-from", "{yesterday}", "--date-to", "{tomorrow}"],
        ["sync-matches", "--competition", "WTA", "--date-from", "{yesterday}", "--date-to", "{tomorrow}"],
        ["sync-kalshi-atp"], ["sync-kalshi-wta"]]
    assert ch["backup"] == "daily" and "active_from" not in ch and "go_on" not in ch
    assert chains.COVERAGE_STEP not in ch["steps"]
    assert {"sync-kalshi-atp", "sync-kalshi-wta"} <= chains.UNMETERED
    assert chains.WINDOW_KALSHI["ATP"] == [["sync-kalshi-atp"]] and chains.WINDOW_KALSHI["WTA"] == [["sync-kalshi-wta"]]
    assert "ATP" not in chains.WINDOW_KALSHI_CAPTURE_ONLY
    src = (HOSTING / "chains.py").read_text()
    blk = src[src.index("# --- TENNIS, market-only"):src.index('"tennis-daily": {')]
    assert "addendum 270 item 5" in blk and "No second writer, ever." in blk and "269 item 3(d)" in blk


def _calendars():
    return {p.stem: re.findall(r"^OnCalendar=(.+)$", p.read_text(), re.M)
            for p in sorted((HOSTING / "systemd").glob("*.timer"))}


def test_the_timer_minute_is_off_every_existing_timer_and_before_the_coverage_write():
    cal = _calendars()
    assert cal["sp-tennis-daily"] == ["*-*-* 06:53:00 UTC"]
    assert "Unit=sp-chain@tennis-daily.service" in (HOSTING / "systemd" / "sp-tennis-daily.timer").read_text()
    minutes = set()
    for name, lines in cal.items():
        if name in ("sp-tennis-daily", "sp-closing-watch"):
            continue
        for ln in lines:
            minutes.add(int(re.search(r"(\d{2}|\*):(\d{2}):00", ln).group(2)))
    assert 53 not in minutes and 53 % 5 != 0, sorted(minutes)
    assert cal["sp-intl-daily"] == ["*-*-* 07:20:00 UTC"] and cal["sp-nba-daily"] == ["*-*-* 06:47:00 UTC"]


def test_the_timer_ships_on_t11_timers_and_the_schedule_table_and_nothing_enables_it():
    import sp_common as c
    lists = c.t11_lists()
    assert "sp-tennis-daily.timer" in lists["TIMERS"] and "sp-tennis-daily.timer" not in lists["MLB_LAPTOP_ONLY"]
    h1 = (ROOT / "docs" / "specs" / "hosting-h1.md").read_text()
    assert len(re.findall(r"^\| sp-tennis-daily \|", h1, re.M)) == 1
    assert "echo sp-tennis-daily.timer | sudo tee -a /etc/sports-predictor/timers.enabled" in h1
    assert "systemctl enable" not in (HOSTING / "install.sh").read_text()          # install.sh enables nothing


def test_the_window_chain_captures_tennis_near_its_kickoff(tmp_path, monkeypatch):
    import sp_common as c
    import sp_run
    now = datetime(2026, 12, 27, 4, 0)
    db = tmp_path / "w.db"
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE competitions(id INTEGER PRIMARY KEY, sport TEXT, code TEXT);"
                      "CREATE TABLE matches(id INTEGER PRIMARY KEY, competition_id INT, season TEXT, status TEXT,"
                      " utc_date TEXT);")
    con.execute("INSERT INTO competitions VALUES (1, 'TENNIS', 'WTA')")
    con.execute("INSERT INTO matches(competition_id, season, status, utc_date) VALUES (1, '2026', 'SCHEDULED', ?)",
                ((now + timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S"),))
    con.commit()
    con.close()
    monkeypatch.setattr(c, "HOST_ENV", tmp_path / "no-host.env")
    monkeypatch.setattr(c, "_DOTENV_CACHE", None)
    monkeypatch.delenv("SP_SKIP_FAMILIES", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    steps = [" ".join(s) for s in sp_run.window_plan(now)["steps"]]
    # the window chain's schedule check is a bounded one-day tennis sync (cli refuses an unbounded one)
    assert "sync-matches --competition WTA --season 2026 --date-from 2026-12-27 --date-to 2026-12-27" in steps
    assert "sync-kalshi-wta" in steps


# ---- the close's record and coverage ------------------------------------------------------------------------------------

def _tennis(s, games):
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    comp = Competition(sport=Sport.TENNIS, code="ATP", name="ATP Tennis Match", area="World", type="LEAGUE")
    s.add(comp)
    s.flush()
    teams = {}
    for gid, home, away, ko, st, res in games:
        for nm in (home, away):
            if nm not in teams:
                teams[nm] = Team(sport=Sport.TENNIS, name=nm)
                s.add(teams[nm])
        s.flush()
        s.add(Match(id=gid, sport=Sport.TENNIS, competition_id=comp.id, season="2026", utc_date=ko,
                    status=st or MatchStatus.SCHEDULED, home_team_id=teams[home].id, away_team_id=teams[away].id,
                    full_time_result=res, status_raw="finalized"))
    s.flush()


def test_the_close_record_scores_tennis_on_the_settlements_winner_never_a_scalar(iso_db):
    """269 item 2: "the settled market says exactly that: the winner by name on yes/no, the fraction on a scalar". A
    tennis row has no score (NULL AND LABELLED), so the record reads full_time_result; a SETTLED_SCALAR row is never
    FINISHED and never read, whatever quotes it holds."""
    from src.db.database import session_scope
    from src.db.schema import MatchStatus, OddsSnapshot, Result
    from src.walters import paper
    ko = Z("2026-12-27T10:00")
    with session_scope() as s:
        _tennis(s, [(9801, "Ana Synthwood", "Bea Fakely", ko, MatchStatus.FINISHED, Result.HOME),
                    (9802, "Cal Mockton", "Dov Testerly", ko, MatchStatus.FINISHED, Result.AWAY),
                    (9803, "Eli Sampleton", "Fay Dummer", ko, MatchStatus.SETTLED_SCALAR, None),
                    (9804, "Gus Oldfield", "Hal Pastly", ko, MatchStatus.FINISHED, None)])
        for mid, bid, ask in ((9801, 0.60, 0.61), (9802, 0.44, 0.45), (9803, 0.50, 0.51), (9804, 0.50, 0.51)):
            s.add(OddsSnapshot(match_id=mid, market="ML", selection="HOME", devig_prob=0.5, n_books=1,
                               captured_at=ko - timedelta(hours=1), source="kalshi", yes_bid=bid, yes_ask=ask))
    rec = paper.close_record(30, now=Z("2026-12-29T12:00"))
    r = rec["ATP"]
    assert r["kind"] == paper.KIND_TWO and r["finished"] == 3 and r["n"] == 2 and r["no_result"] == 1
    assert r["ll_sum"] == pytest.approx(-math.log(0.605) - math.log(1 - 0.445))
    assert rec["WTA"]["finished"] == 0
    assert "ATP n=2" in paper.close_record_console(rec, 30)


def test_coverage_prints_tennis_market_only_with_paper_lines(env, monkeypatch):
    monkeypatch.setitem(tcm.COMPS, "ATP", 98)
    tcm.make_db(env, [(951, "ATP", "2026-10-17 10:00", "SCHEDULED"),
                     (952, "ATP", "2026-10-17 11:00", "FINISHED"),
                     (953, "ATP", "2026-10-17 12:00", "SETTLED_SCALAR")])
    rc, out = tcm.run("--date", tcm.DAY)
    assert rc == 0, out
    atp = tcm.line_of(out, "ATP")
    assert atp.startswith("ATP · 3 games · MARKET-ONLY ("), atp
    assert "export._MARKET_ONLY_REASON" in atp
    assert any(x.startswith("ATP SLATE · PAPER, never a call") for x in out), out


# ---- the docs name what was built ---------------------------------------------------------------------------------------

def test_the_docs_name_the_commands_the_chain_and_the_receipt():
    doc = (ROOT / "docs" / "CLI.md").read_text()
    assert "| `sync-kalshi-atp` · `sync-kalshi-wta` |" in doc and "**Tennis daily (host `sp-tennis-daily`" in doc
    assert "| `python3 scripts/tennis_certification_receipt.py` |" in doc
    row = next(ln for ln in doc.splitlines() if ln.startswith("| `sync-kalshi-atp` · `sync-kalshi-wta` |"))
    assert "addendum 274 item 1(b)" in row and "(1.0, 1.0)" in row and "never guessed" in row
    assert "ATP (`KXATPMATCH`) and WTA (`KXWTAMATCH`)" in doc
