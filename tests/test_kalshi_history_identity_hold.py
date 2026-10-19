"""THE IDENTITY HOLD on the settled-history path (ARCHITECT 2026-10-18, addendum 127 item 3(c), standing by addendum 130
item 2(c)) and the ruled RE-PLACE, `kalshi-history place-held` (addendum 130 item 2(c)).

The world is the ALCS pair of #476 as addendum 130 item 1 records it, written here (synthetic markets, a throwaway DB
of its own per test): 50546 = Game 3, played 2026-10-15; 50550 = played 2026-10-17 20:08 ET (now Game 4, Rays 7-3);
50548 = the 10-16 game, postponed to 2026-10-18 21:08Z (now Game 5). KXMLBGAME-26OCT151800TBCLE settled on Game 3;
26OCT161800TBCLE settled 2026-10-18 03:20Z, Tampa Bay yes; 26OCT172000TBCLE settles after tonight's game (its result
here is a placeholder: no test reads it)."""
import sqlite3
from datetime import date, datetime, timedelta, timezone

import pytest
import requests
from click.testing import CliRunner
from sqlalchemy import inspect, select, text

from src.adapters.kalshi import KalshiAdapter
from src.ingestion import kalshi_history as kh
from src.ingestion import kalshi_match as km

S = "KXMLBGAME"
E15, E16, E17 = (f"{S}-26OCT151800TBCLE", f"{S}-26OCT161800TBCLE", f"{S}-26OCT172000TBCLE")
G3, G4, G5 = 50546, 50550, 50548                 # Game 3; the game played Saturday night; the postponed one
NOW = datetime(2026, 10, 19, 12, 0)              # Monday's pull
RULING = "ARCHITECT 2026-10-18, addendum 130 item 2(c)"


def _ts(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def market(ev, sfx, name, result, close, settled, status="finalized"):
    return {"ticker": f"{ev}-{sfx}", "event_ticker": ev, "yes_sub_title": name, "title": f"{name} wins",
            "result": result, "close_time": close, "settlement_ts": settled, "status": status}


def event(ev, tb, close=None, settled=None, status="finalized", names=("Tampa Bay", "Cleveland")):
    """One event's two legs: TB's result `tb` ('yes' / 'no' / '' for an open market), CLE's the other."""
    other = {"yes": "no", "no": "yes"}.get(tb, tb)
    return [market(ev, "TB", names[0], tb, close, settled, status),
            market(ev, "CLE", names[1], other, close, settled, status)]


SETTLED15 = event(E15, "no", "2026-10-15T20:10:00Z", "2026-10-15T20:15:00Z")
SETTLED16 = event(E16, "yes", "2026-10-18T03:18:00Z", "2026-10-18T03:20:00Z")
SETTLED17 = event(E17, "yes", "2026-10-19T00:40:00Z", "2026-10-19T00:45:00Z")         # placeholder result
OPEN16 = event(E16, "", "2026-10-21T03:00:00Z", None, status="active")


def candles_at(kickoff, bid="0.45", ask="0.46", n=5):
    """Live-shape one-minute candles up to `kickoff` (written here: two-sided, the live shape's own keys)."""
    return [{"end_period_ts": _ts(kickoff) - 60 * k, "yes_bid": {"close_dollars": bid},
             "yes_ask": {"close_dollars": ask}} for k in range(n)]


class Fake(KalshiAdapter):
    """The exchange as the tests write it: the cutoff, an empty historical list, the live settled list, the open list
    and one candle reply per market (by ticker); `fail` answers a candle call with an HTTP status, raises an exception
    given there (a transport error), or answers "no list" with a 200 that holds no candles list."""

    def __init__(self, settled=(), opened=(), candles=None, fail=None):
        super().__init__()
        self.settled, self.opened = list(settled), list(opened)
        self.candles, self.fail, self.calls = candles or {}, fail or {}, []

    def _get(self, path, params=None):
        params = dict(params or {})
        self.calls.append((path, params))
        if path == "historical/cutoff":
            return {"market_settled_ts": "2026-08-15T00:00:00Z"}
        if path == "historical/markets":
            return {"markets": [], "cursor": ""}
        if path == "markets":
            return {"markets": {"settled": self.settled, "open": self.opened}.get(params.get("status"), []),
                    "cursor": ""}
        if path.endswith("/candlesticks"):
            t = path.rsplit("/", 2)[-2]
            if t in self.fail:
                if isinstance(self.fail[t], Exception):
                    raise self.fail[t]
                if self.fail[t] == "no list":
                    return {"ticker": t}
                resp = requests.Response()
                resp.status_code = self.fail[t]
                raise requests.HTTPError(response=resp)
            return {"candlesticks": self.candles.get(t, []), "ticker": t}
        raise AssertionError(f"unexpected call {path}")

    def candle_calls(self):
        return {p.rsplit("/", 2)[-2]: q for p, q in self.calls if p.endswith("/candlesticks")}

    def open_calls(self):
        return [q for p, q in self.calls if p == "markets" and q.get("status") == "open"]


@pytest.fixture(autouse=True)
def waits(monkeypatch):
    """Addendum 104 item 2's waits before a 429 is asked again, recorded instead of slept."""
    got = []
    monkeypatch.setattr(kh, "_wait", got.append)
    return got


@pytest.fixture
def db(tmp_path, monkeypatch):
    """A throwaway DB of its own (the app's engine and the mode=ro reader both point at it), migrated
    (migrate_kalshi_settled_markets.py, marker and all)."""
    import importlib.util
    from pathlib import Path

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as dbm
    from src.walters import venue_quote_age
    path = tmp_path / "fresh.db"
    eng = create_engine(f"sqlite:///{path}", future=True)
    monkeypatch.setattr(dbm, "_engine", eng)
    monkeypatch.setattr(dbm, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                          expire_on_commit=False))
    monkeypatch.setattr(venue_quote_age, "db_file_path", lambda: path)
    dbm.init_db()
    spec = importlib.util.spec_from_file_location("mig", Path(__file__).resolve().parents[1]
                                                  / "migrate_kalshi_settled_markets.py")
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    assert mig.main() == 0
    return path


def seed(games, code="MLB", sport="MLB"):
    """{id: (away, home, kickoff UTC, status)} in competition `code` (made when missing)."""
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == code)).scalar_one_or_none()
        if comp is None:
            comp = Competition(sport=Sport[sport], code=code, name=code, area="USA", type="LEAGUE")
            s.add(comp)
            s.flush()
        teams = {t.name: t for t in s.execute(select(Team)).scalars()}
        for gid, (away, home, kick, status) in games.items():
            for n in (away, home):
                if n not in teams:
                    teams[n] = Team(sport=Sport[sport], name=n)
                    s.add(teams[n])
            s.flush()
            s.add(Match(id=gid, sport=Sport[sport], competition_id=comp.id, season="2026", utc_date=kick,
                        status=MatchStatus(status), home_team_id=teams[home].id, away_team_id=teams[away].id))


def redate(gid, kick):
    from src.db.database import session_scope
    from src.db.schema import Match
    with session_scope() as s:
        s.get(Match, gid).utc_date = kick


TB, CLE = "Tampa Bay Rays", "Cleveland Guardians"
K3, K4, K5 = datetime(2026, 10, 15, 17, 0), datetime(2026, 10, 18, 0, 8), datetime(2026, 10, 18, 21, 8)


@pytest.fixture
def alcs(db):
    """Addendum 130 item 1's rows: Game 3 on 10-15; 50550 played 10-17 20:08 ET; 50548 moved to 10-18 21:08Z."""
    seed({G3: (TB, CLE, K3, "finished"), G4: (TB, CLE, K4, "finished"), G5: (TB, CLE, K5, "scheduled")})
    return db


def rows():
    from src.db.database import session_scope
    from src.db.schema import KalshiSettledMarket
    with session_scope() as s:
        return {r.ticker: {c: getattr(r, c) for c in KalshiSettledMarket.__table__.c.keys()}
                for r in s.execute(select(KalshiSettledMarket)).scalars()}


def go(fake, **kw):
    out = []
    run = kh.run_history(S, echo=out.append, adapter=fake, now=kw.pop("now", NOW), **kw)
    return run, out


def hold(ev, why):
    return kh.HOLD_NOTE.format(event=ev, why=why)


# ---- the hold -------------------------------------------------------------------------------------------------------

def test_the_monday_pull_holds_26oct172000_behind_26oct161800_out_of_step(alcs):
    """127 item 3(c), the receipt's shape: once 26OCT172000TBCLE settles, main stores it by date on 50550 for good. Here
    its earlier event 26OCT161800TBCLE is out of step on its own date (no game of the pair on 10-16), so it is kept
    with match_id and side null and the ruled reason; no candle is fetched for it. 26OCT151800TBCLE is placed on Game 3
    and 26OCT161800TBCLE keeps its own refusal."""
    fake = Fake(settled=SETTLED15 + SETTLED16 + SETTLED17, candles={f"{E15}-TB": candles_at(K3)})
    run, out = go(fake)
    got = rows()
    for sfx in ("TB", "CLE"):
        r = got[f"{E17}-{sfx}"]
        assert (r["match_id"], r["side"], r["last_ts"], r["candles_6h"]) == (None, None, None, None)
        assert r["notes"] == f"{hold(E16, 'out of step')}; {kh.HOLD_NO_CANDLES}"
        assert kh.is_held(r["match_id"], r["notes"])
        assert f"{E17}-{sfx}" not in fake.candle_calls()
        assert got[f"{E16}-{sfx}"]["notes"].startswith(f"refused by the matcher: {km.NO_GAME_ON_DATE}")
        assert not kh.is_held(got[f"{E16}-{sfx}"]["match_id"], got[f"{E16}-{sfx}"]["notes"])
    assert (got[f"{E15}-TB"]["match_id"], got[f"{E15}-TB"]["side"]) == (G3, "AWAY")
    assert (got[f"{E15}-CLE"]["match_id"], got[f"{E15}-CLE"]["side"]) == (G3, "HOME")
    assert run.held_new == 2 and run.refused == {km.NO_GAME_ON_DATE: 2}
    assert f"  ⏸ {E17}: {hold(E16, 'out of step')} (no game of its two teams on its date 2026-10-16); held, not " \
           f"placed by date: {E17}-CLE, {E17}-TB" in out


def test_an_earlier_event_still_open_holds_the_later_one_unsettled(alcs):
    """The other half: 26OCT161800TBCLE in step (a game of the pair on 10-16) but still listed open when
    26OCT172000TBCLE has settled; by date the later one would take 50550. It is held "unsettled"."""
    redate(G5, datetime(2026, 10, 17, 0, 0))                                          # 8pm ET 10-16, unmoved
    fake = Fake(settled=SETTLED15 + SETTLED17, opened=OPEN16)
    run, out = go(fake, dry_run=True)
    held = {r["ticker"]: r for r in run.rows if r["ticker"].startswith(E17)}
    assert len(held) == 2 and all(r["match_id"] is None for r in held.values())
    assert all(r["notes"].startswith(hold(E16, "unsettled")) for r in held.values())
    assert f"  ⏸ {E17}: {hold(E16, 'unsettled')} (the exchange lists it open); held, not placed by date: " \
           f"{E17}-CLE, {E17}-TB" in out
    assert fake.open_calls() == [{"series_ticker": S, "status": "open", "limit": kh.PAGE_LIMIT}]
    assert all(not r["ticker"].startswith(E16) for r in run.rows)                     # an open market is never stored


@pytest.mark.parametrize("days, why, binds", [
    (10, "out of step", True),                    # the bound's edge: 10 days before binds
    (11, "out of step", False),                   # 11 does not
    (30, "out of step", False),                   # a regular-season rainout's shape, a month before: holds nothing now
    (10, "unsettled", True),
    (11, "unsettled", False),
], ids=["out-of-step-10d-binds", "out-of-step-11d-not", "rainout-30d-not", "unsettled-10d-binds", "unsettled-11d-not"])
def test_an_earlier_event_binds_only_within_ten_days_before(alcs, days, why, binds):
    """Addendum 132 item 3(c), THE BOUND ON "EARLIER-DATED": "an earlier event of the pair binds only when its ticker
    date is within 10 days before the event's date. A series never spans more than that (a seven-game series runs nine
    days); a regular-season rainout in May would otherwise hold every later event of the pair for the season." The
    earlier event here is a rainout's shape: its game was played the next day, so it is out of step on its own date
    (or, the other half, it is still listed open). 26OCT161800TBCLE is in step (50547 on 10-16), so only the older
    event can hold 26OCT172000TBCLE: at 10 days it binds, at 11 and at 30 it does not, and 26OCT172000TBCLE is placed by
    date on 50550."""
    seed({G2: (TB, CLE, K2, "finished")})
    d0 = date(2026, 10, 17) - timedelta(days=days)
    e0 = f"{S}-{d0:%y%b%d}".upper() + "1810TBCLE"
    seed({50600 + days: (TB, CLE, datetime(d0.year, d0.month, d0.day, 23, 10) + timedelta(days=1), "finished")})
    old = (event(e0, "", "2026-10-25T03:00:00Z", None, status="active") if why == "unsettled"
           else event(e0, "yes", f"{d0 + timedelta(days=2)}T03:00:00Z", f"{d0 + timedelta(days=2)}T03:05:00Z"))
    fake = Fake(settled=SETTLED15 + SETTLED16 + SETTLED17 + ([] if why == "unsettled" else old),
                opened=old if why == "unsettled" else [])
    run, out = go(fake, dry_run=True, since=date(2026, 10, 17))
    got = {r["ticker"]: r for r in run.rows}
    assert set(got) == {f"{E17}-TB", f"{E17}-CLE"}
    if binds:
        assert all((r["match_id"], r["side"]) == (None, None) and r["notes"].startswith(hold(e0, why))
                   for r in got.values())
        assert run.held_new == 2 and any(ln.startswith(f"  ⏸ {E17}: {hold(e0, why)} (") for ln in out)
    else:
        assert (got[f"{E17}-TB"]["match_id"], got[f"{E17}-TB"]["side"]) == (G4, "AWAY")
        assert (got[f"{E17}-CLE"]["match_id"], got[f"{E17}-CLE"]["side"]) == (G4, "HOME")
        assert run.held_new == 0 and not any(ln.startswith("  ⏸ ") for ln in out)


def test_the_receipt_s_lines(alcs):
    """The markets listed line counts the open list apart from the settled ones; the hold has its own section, under
    the stored line, apart from the matcher's refusals."""
    fake = Fake(settled=SETTLED15 + SETTLED16 + SETTLED17, opened=event(f"{S}-26OCT191600CLETB", ""))
    run, out = go(fake, dry_run=True)
    assert "  markets listed: 6 (historical 0, live settled 6) · open, read for the identity hold only (never placed " \
           "or stored) 2" in out
    assert "  would be stored: 6 (placed on a stored game 2, refused and kept 4) · already stored 0" in out
    i = out.index("  would be stored: 6 (placed on a stored game 2, refused and kept 4) · already stored 0")
    assert out[i + 1] == ("  identity hold (clock series; ARCHITECT 2026-10-18, addendum 127 item 3(c)): new rows held 2 "
                          "(kept with match_id null; a later run reads them again) · stored held rows held again 0 "
                          "(left as stored) · stored held rows would be placed, the hold cleared 0")
    assert out[i + 2].startswith(f"  ⏸ {E17}: ")
    assert out[i + 3] == "  refused by the matcher, by reason (kept with match_id null):"
    assert out[i + 4] == f"        2  {km.NO_GAME_ON_DATE}"
    assert f"        2  {kh.HOLD_NO_CANDLES}" in out


def test_a_date_only_series_is_untouched(db, monkeypatch):
    """No clock in the ticker (NFL, NHL, NCAA, the soccer series): no hold and no open list. An earlier event of the
    pair with no game near its date holds nothing; the later one is placed by the day rule, as before."""
    from src.walters import venue
    monkeypatch.setitem(venue.KALSHI_SERIES_BY_COMPETITION, "ZDO", "KXZDOGAME")
    seed({901: ("Alpha Owls", "Beta Bears", datetime(2026, 10, 20, 23, 0), "finished")}, code="ZDO", sport="NHL")
    old = [market("KXZDOGAME-26OCT10ALPBET", "ALP", "Alpha", "yes", "2026-10-11T03:00:00Z", "2026-10-11T03:05:00Z"),
           market("KXZDOGAME-26OCT10ALPBET", "BET", "Beta", "no", "2026-10-11T03:00:00Z", "2026-10-11T03:05:00Z")]
    new = [market("KXZDOGAME-26OCT20ALPBET", "ALP", "Alpha", "yes", "2026-10-21T03:00:00Z", "2026-10-21T03:05:00Z"),
           market("KXZDOGAME-26OCT20ALPBET", "BET", "Beta", "no", "2026-10-21T03:00:00Z", "2026-10-21T03:05:00Z")]
    fake = Fake(settled=old + new)
    out = []
    run = kh.run_history("KXZDOGAME", echo=out.append, adapter=fake, now=NOW, dry_run=True)
    placed = {r["ticker"]: (r["match_id"], r["side"]) for r in run.rows}
    assert placed["KXZDOGAME-26OCT20ALPBET-ALP"] == (901, "AWAY")
    assert placed["KXZDOGAME-26OCT10ALPBET-ALP"] == (None, None) and run.refused == {km.NO_FIT: 2}
    assert fake.open_calls() == [] and not run.open_read and run.held_new == 0
    assert not any("identity hold" in ln for ln in out)


def test_an_already_placed_row_is_never_moved(alcs):
    """A row stored with a match_id (here 26OCT172000TBCLE on 50550, as main would have stored it) is skipped by every
    later run, whatever the hold says now: nothing already placed is moved by the ingest."""
    go(Fake(settled=SETTLED15 + SETTLED16))
    from src.db.database import session_scope
    from src.db.schema import KalshiSettledMarket
    with session_scope() as s:
        for sfx, side in (("TB", "AWAY"), ("CLE", "HOME")):
            s.add(KalshiSettledMarket(ticker=f"{E17}-{sfx}", event_ticker=E17, series=S, side=side, match_id=G4,
                                      yes_sub_title={"TB": "Tampa Bay", "CLE": "Cleveland"}[sfx], source="live",
                                      fetched_at=datetime(2026, 10, 19, 6, 0), notes=None))
    before = rows()
    fake = Fake(settled=SETTLED15 + SETTLED16 + SETTLED17)
    run, out = go(fake)
    assert rows() == before and run.already == 6 and not run.rows and not run.replaced
    assert not fake.candle_calls() and not any(ln.startswith("  ⏸ ") for ln in out)


def test_a_held_row_is_placed_by_a_later_run_once_the_hold_clears(alcs):
    """The one exception to "inserted once": run 1 holds 26OCT172000TBCLE behind 26OCT161800TBCLE, open. Run 2 lists
    26OCT161800TBCLE settled, in step on its own date: the hold has cleared, so the stored held rows are placed as the
    ingest places a new event (the stored kickoff's candles fetched then) and the clearing is appended to their notes.
    Run 3 reads them no more."""
    redate(G5, datetime(2026, 10, 17, 0, 0))
    go(Fake(settled=SETTLED15 + SETTLED17, opened=OPEN16))
    assert all(kh.is_held(r["match_id"], r["notes"]) for t, r in rows().items() if t.startswith(E17))
    fake = Fake(settled=SETTLED15 + SETTLED16 + SETTLED17, candles={f"{E17}-TB": candles_at(K4, "0.51", "0.53")})
    run, out = go(fake, now=datetime(2026, 10, 20, 12, 0))
    got = rows()
    tb, cle = got[f"{E17}-TB"], got[f"{E17}-CLE"]
    assert (tb["match_id"], tb["side"], cle["match_id"], cle["side"]) == (G4, "AWAY", G4, "HOME")
    assert tb["notes"] == (f"{hold(E16, 'unsettled')}; {kh.HOLD_NO_CANDLES}; hold cleared 2026-10-20 12:00Z: placed by "
                           "the ingest")
    assert cle["notes"].endswith("hold cleared 2026-10-20 12:00Z: placed by the ingest; no two-sided candle at or "
                                 "before kickoff")
    assert (tb["last_bid"], tb["last_ask"], tb["last_ts"]) == (0.51, 0.53, K4)
    assert tb["fetched_at"] == datetime(2026, 10, 20, 12, 0)
    assert fake.candle_calls()[f"{E17}-TB"]["start_ts"] == _ts(datetime(2026, 10, 17, 18, 8))   # 50550's kickoff - 6h
    assert (got[f"{E16}-TB"]["match_id"], got[f"{E16}-TB"]["side"]) == (G5, "AWAY")             # new, in step
    assert len(run.replaced) == 2 and run.already == 2 and len(run.rows) == 2          # 26OCT151800 skipped
    assert any("stored held rows placed, the hold cleared 2" in ln for ln in out)
    # the null totals count every row the run writes, the placed held rows included (Codex review on #598: they read
    # run.rows only, so the cleared -CLE row stored with no quote went uncounted): 26OCT161800's two new rows have no
    # candles, and 26OCT172000-CLE has none two-sided
    assert "  rows with last_ts null (no two-sided candle before kickoff, or no candles): 3" in out
    assert "  rows with settled_time null: 0" in out
    run3, _ = go(Fake(settled=SETTLED15 + SETTLED16 + SETTLED17), now=datetime(2026, 10, 21, 12, 0))
    assert rows() == got and run3.already == 6 and not run3.replaced


def test_a_held_row_held_again_or_refused_once_cleared_is_left_as_stored(alcs):
    """Held again: left exactly as stored. Hold cleared but refused by the matcher for a reason of its own: left as
    stored too (the ingest writes a held row only to place it), and listed."""
    go(Fake(settled=SETTLED15 + SETTLED16 + SETTLED17))
    first = rows()
    run, out = go(Fake(settled=SETTLED15 + SETTLED16 + SETTLED17), now=datetime(2026, 10, 20, 12, 0))
    assert rows() == first and run.held_still == 2 and not run.replaced
    assert any("stored held rows held again 2 (left as stored)" in ln for ln in out)
    # 50550 re-dated off 10-17 and 50548 back onto 10-16: 26OCT161800TBCLE is in step, so the hold clears; but no game
    # of the pair is on 26OCT172000TBCLE's own date any more, and the matcher refuses it
    redate(G5, datetime(2026, 10, 17, 0, 0))
    redate(G4, datetime(2026, 10, 19, 0, 8))
    run, out = go(Fake(settled=SETTLED15 + SETTLED16 + SETTLED17), now=datetime(2026, 10, 21, 12, 0))
    assert {t: r for t, r in rows().items() if t.startswith(E17)} == {t: r for t, r in first.items()
                                                                      if t.startswith(E17)}
    assert sorted(run.held_refused) == [(f"{E17}-CLE", km.NO_GAME_ON_DATE), (f"{E17}-TB", km.NO_GAME_ON_DATE)]
    assert f"    {E17}-TB: hold cleared; refused by the matcher: {km.NO_GAME_ON_DATE}" in out


G2 = 50547                                       # a TB@CLE game on 10-16 18:00 ET: 26OCT161800TBCLE in step
K2 = datetime(2026, 10, 16, 22, 0)
E18 = f"{S}-26OCT181708TBCLE"                    # 17:08 ET 10-18 = 21:08Z, 50548's kickoff
SETTLED18 = event(E18, "yes", "2026-10-19T01:40:00Z", "2026-10-19T01:45:00Z")


def _claims():
    on = {}
    for t, r in rows().items():
        if r["match_id"] is not None:
            on.setdefault((r["match_id"], r["side"]), []).append(t)
    return on


def test_a_cleared_held_row_is_not_placed_on_a_side_a_ruled_row_holds(alcs):
    """The claims rule reads the stored rows too (verifier P2 on this PR): run 1 holds 26OCT172000TBCLE and
    26OCT181708TBCLE behind 26OCT161800TBCLE, open; a ruling places 26OCT172000TBCLE on 50548; run 2 lists
    26OCT161800TBCLE settled, in step on 10-16, so 26OCT181708TBCLE's hold clears and by date it goes to 50548, the
    sides the ruled rows hold. It is refused under the matcher's claims rule and left as stored (still a held row);
    the ruled rows are not moved; no side of any game carries two rows."""
    seed({G2: (TB, CLE, K2, "finished")})
    go(Fake(settled=SETTLED15 + SETTLED17 + SETTLED18, opened=OPEN16))
    assert all(kh.is_held(r["match_id"], r["notes"]) for t, r in rows().items() if t.startswith((E17, E18)))
    place(f"{E17}-TB", G5)
    place(f"{E17}-CLE", G5)
    before = rows()
    fake = Fake(settled=SETTLED15 + SETTLED16 + SETTLED17 + SETTLED18)
    run, out = go(fake, now=datetime(2026, 10, 20, 12, 0))
    got = rows()
    assert {k: v for k, v in _claims().items() if len(v) > 1} == {}
    for sfx, side in (("TB", "AWAY"), ("CLE", "HOME")):
        assert got[f"{E18}-{sfx}"] == before[f"{E18}-{sfx}"]                  # left as stored: still a held row
        assert got[f"{E17}-{sfx}"] == before[f"{E17}-{sfx}"]                  # the ruled row is not moved
        assert (got[f"{E17}-{sfx}"]["match_id"], got[f"{E17}-{sfx}"]["side"]) == (G5, side)
        assert (got[f"{E16}-{sfx}"]["match_id"], got[f"{E16}-{sfx}"]["side"]) == (G2, side)   # new, in step
    assert not run.replaced
    assert sorted(run.held_refused) == [(f"{E18}-CLE", km.TWO_CLAIMS), (f"{E18}-TB", km.TWO_CLAIMS)]
    assert f"    {E18}-TB: hold cleared; refused by the matcher: {km.TWO_CLAIMS} (match {G5} AWAY is stored on " \
           f"{E17}-TB)" in out
    assert not any(t.startswith(E18) for t in fake.candle_calls())             # nothing of it read or written


def test_a_new_row_is_not_placed_on_a_side_a_ruled_row_holds(alcs):
    """The same rule for a market listed for the first time: 26OCT181708TBCLE first listed in run 2, placed by date on
    50548, whose sides the ruled rows of 26OCT172000TBCLE hold. It is stored refused, under the matcher's claims
    rule, and the refusal names the stored row."""
    seed({G2: (TB, CLE, K2, "finished")})
    go(Fake(settled=SETTLED15 + SETTLED17, opened=OPEN16))
    place(f"{E17}-TB", G5)
    place(f"{E17}-CLE", G5)
    before = rows()
    run, out = go(Fake(settled=SETTLED15 + SETTLED16 + SETTLED17 + SETTLED18), now=datetime(2026, 10, 20, 12, 0))
    got = rows()
    assert {k: v for k, v in _claims().items() if len(v) > 1} == {}
    for sfx in ("TB", "CLE"):
        r = got[f"{E18}-{sfx}"]
        assert (r["match_id"], r["side"]) == (None, None)
        assert r["notes"].startswith(f"refused by the matcher: {km.TWO_CLAIMS}")
        assert got[f"{E17}-{sfx}"] == before[f"{E17}-{sfx}"]
    assert run.refused[km.TWO_CLAIMS] == 2
    assert f"  ✗ match {G5} AWAY: stored on {E17}-TB (nothing already placed is moved); {E18}-TB claims it too: " \
           "refused" in out


def test_the_write_reads_the_side_again(alcs):
    """At the write a re-placed held row is checked again, as place-held checks it: a side another row of the series
    took after the run read the table (here during the candle calls) is not written over; the held row is left as it
    is, and the receipt says why."""
    from src.db.database import session_scope
    from src.db.schema import KalshiSettledMarket
    redate(G5, datetime(2026, 10, 17, 0, 0))
    go(Fake(settled=SETTLED15 + SETTLED17, opened=OPEN16))
    before = rows()

    class Race(Fake):
        def _get(self, path, params=None):
            if path.endswith(f"/{E17}-TB/candlesticks"):
                with session_scope() as s:
                    s.add(KalshiSettledMarket(ticker=f"{S}-26OCT171900TBCLE-TB", event_ticker=f"{S}-26OCT171900TBCLE",
                                              series=S, side="AWAY", match_id=G4, yes_sub_title="Tampa Bay",
                                              source="live", fetched_at=NOW, notes="placed by ruling: test"))
            return super()._get(path, params)
    run, out = go(Race(settled=SETTLED15 + SETTLED16 + SETTLED17), now=datetime(2026, 10, 20, 12, 0))
    got = rows()
    assert got[f"{E17}-TB"] == before[f"{E17}-TB"]
    assert (got[f"{E17}-CLE"]["match_id"], got[f"{E17}-CLE"]["side"]) == (G4, "HOME")
    assert run.replace_skipped == [(f"{E17}-TB", f"match {G4} AWAY is held by {S}-26OCT171900TBCLE-TB at the write "
                                                 "(two settled markets are never stored on one side of one game)")]
    assert f"  ✗ {E17}-TB: match {G4} AWAY is held by {S}-26OCT171900TBCLE-TB at the write (two settled markets are " \
           "never stored on one side of one game): left as it is" in out
    assert {k: v for k, v in _claims().items() if len(v) > 1} == {}


def test_a_new_clock_row_is_not_placed_on_a_side_a_date_placed_row_holds(alcs):
    """The claims rule's scope, its clock half: on a clock series a stored row refuses a new market on its side however
    it was placed. Here 26OCT172000TBCLE is stored on 50548 as a date placement would store it (no ruling in its
    notes); 26OCT181708TBCLE, first listed in run 2 and placed by date on 50548, is stored refused."""
    from src.db.database import session_scope
    from src.db.schema import KalshiSettledMarket
    seed({G2: (TB, CLE, K2, "finished")})
    go(Fake(settled=SETTLED15 + SETTLED16))
    with session_scope() as s:
        for sfx, side in (("TB", "AWAY"), ("CLE", "HOME")):
            s.add(KalshiSettledMarket(ticker=f"{E17}-{sfx}", event_ticker=E17, series=S, side=side, match_id=G5,
                                      yes_sub_title={"TB": "Tampa Bay", "CLE": "Cleveland"}[sfx], source="live",
                                      fetched_at=datetime(2026, 10, 19, 6, 0), notes=None))
    before = rows()
    run, out = go(Fake(settled=SETTLED15 + SETTLED16 + SETTLED17 + SETTLED18), now=datetime(2026, 10, 20, 12, 0))
    got = rows()
    assert {k: v for k, v in _claims().items() if len(v) > 1} == {}
    for sfx in ("TB", "CLE"):
        assert (got[f"{E18}-{sfx}"]["match_id"], got[f"{E18}-{sfx}"]["side"]) == (None, None)
        assert got[f"{E18}-{sfx}"]["notes"].startswith(f"refused by the matcher: {km.TWO_CLAIMS}")
        assert got[f"{E17}-{sfx}"] == before[f"{E17}-{sfx}"]
    assert run.refused == {km.TWO_CLAIMS: 2}
    assert f"  ✗ match {G5} AWAY: stored on {E17}-TB (nothing already placed is moved); {E18}-TB claims it too: " \
           "refused" in out


E17B = f"{S}-26OCT172010TBCLE"                   # a second event of the pair dated 10-17 (20:10 ET): by date on 50550


def test_a_stored_row_enters_the_claims_rule_by_its_stored_side_never_by_its_date(alcs):
    """Addendum 132 item 3(b): "The in-run claims rule reads a STORED row by its stored (match_id, side), never by
    re-placing it by date. ... Stored rows enter the claims rule as stored; only the run's new markets and the held rows
    it places are placed by date." 26OCT172000TBCLE is placed by ruling on 50548 (X); its ticker date would place it on
    50550 (Y). Run 2 lists it again beside two new events: 26OCT172010TBCLE, placed by date on Y, is placed there (the
    stored row's date is not read, so it claims nothing on Y); 26OCT181708TBCLE, placed by date on X, is refused on the
    sides the stored row holds as stored. The ruled rows are not moved; no side of any game carries two rows."""
    _monday(alcs)
    for sfx in ("TB", "CLE"):
        assert place(f"{E17}-{sfx}", G5)[0]["written"]
    seed({G2: (TB, CLE, K2, "finished")})        # 26OCT161800TBCLE in step on 10-16: nothing earlier holds the new events
    before = rows()
    fake = Fake(settled=SETTLED15 + SETTLED16 + SETTLED17 + SETTLED18
                + event(E17B, "yes", "2026-10-18T03:30:00Z", "2026-10-18T03:35:00Z"),
                candles={f"{E17B}-TB": candles_at(K4, "0.52", "0.54")})
    run, out = go(fake, now=datetime(2026, 10, 20, 12, 0))
    got = rows()
    assert {k: v for k, v in _claims().items() if len(v) > 1} == {}
    for sfx, side in (("TB", "AWAY"), ("CLE", "HOME")):
        assert got[f"{E17}-{sfx}"] == before[f"{E17}-{sfx}"]                  # the ruled row, as stored
        assert (got[f"{E17B}-{sfx}"]["match_id"], got[f"{E17B}-{sfx}"]["side"]) == (G4, side)      # Y: placed
        assert (got[f"{E18}-{sfx}"]["match_id"], got[f"{E18}-{sfx}"]["side"]) == (None, None)      # X: refused
        assert got[f"{E18}-{sfx}"]["notes"].startswith(f"refused by the matcher: {km.TWO_CLAIMS}")
    assert got[f"{E17B}-TB"]["last_bid"] == 0.52
    assert run.refused == {km.TWO_CLAIMS: 2}
    assert f"  ✗ match {G5} AWAY: stored on {E17}-TB (nothing already placed is moved); {E18}-TB claims it too: " \
           "refused" in out
    assert not any(f"{E17B}-TB" in ln and "claim" in ln for ln in out)


# ---- the claims rule on a date-only series: NCAA's Friday-dated twins (addendum 130 item 3(b)) ----------------------

N16, N17 = "KXNCAAFGAME-26OCT16FLATEX", "KXNCAAFGAME-26OCT17FLATEX"     # the day-off twin; the own-date event
NG = 2001                                                                   # Florida at Texas, Saturday 10-17
NK = datetime(2026, 10, 17, 19, 30)


def ncaa(ev):
    """One NCAA event's two legs as the 52 refused rows' pairs settled: Saturday evening, the Saturday game's result."""
    return [market(ev, "FLA", "Florida", "no", "2026-10-18T03:00:00Z", "2026-10-18T03:10:00Z"),
            market(ev, "TEX", "Texas", "yes", "2026-10-18T03:00:00Z", "2026-10-18T03:10:00Z")]


def ncaa_go(fake, **kw):
    out = []
    run = kh.run_history("KXNCAAFGAME", echo=out.append, adapter=fake, now=kw.pop("now", NOW), **kw)
    return run, out


def test_a_date_only_series_places_the_own_date_event_across_runs_as_main_does(db):
    """The claims rule's scope (a verifier's P2 on this branch, reproduced): it reads a stored row's side only on a
    clock series or where a ruled row holds the side, so a date-only series stays as main has it. Run 1 (--until
    2026-10-16) stores the day-off twin 26OCT16FLATEX, placed by date on the Saturday game; run 2 (--since 2026-10-17)
    lists the own-date event 26OCT17FLATEX, which addendum 130 item 3(b) says keeps its sides. It is placed there, as
    main places it; nothing is refused and no claims line is printed. That leaves the twins on one side of one game
    across the runs, main's state: the day-off twin is the NCAA tiebreak PR's (130 item 3(b)), not this one's."""
    from datetime import date
    seed({NG: ("Florida Gators", "Texas Longhorns", NK, "finished")}, code="NCAA", sport="NFL")
    fake = Fake(settled=ncaa(N16) + ncaa(N17))
    ncaa_go(fake, until=date(2026, 10, 16))
    assert {t: (r["match_id"], r["side"]) for t, r in rows().items()} == {f"{N16}-FLA": (NG, "AWAY"),
                                                                           f"{N16}-TEX": (NG, "HOME")}
    run, out = ncaa_go(Fake(settled=ncaa(N16) + ncaa(N17)), since=date(2026, 10, 17))
    got = rows()
    for sfx, side in (("FLA", "AWAY"), ("TEX", "HOME")):
        assert (got[f"{N17}-{sfx}"]["match_id"], got[f"{N17}-{sfx}"]["side"]) == (NG, side)
        assert "refused" not in (got[f"{N17}-{sfx}"]["notes"] or "")
    assert run.refused == {} and run.claimed_by == {} and len(run.rows) == 2
    assert not any(" stored on " in ln or "identity hold" in ln for ln in out)
    assert {k: sorted(v) for k, v in _claims().items()} == {(NG, "AWAY"): [f"{N16}-FLA", f"{N17}-FLA"],
                                                            (NG, "HOME"): [f"{N16}-TEX", f"{N17}-TEX"]}


def test_a_date_only_side_a_ruled_row_holds_still_refuses(db):
    """The claims rule's scope, its ruled half: on a date-only series a side that a row placed by ruling holds
    (place-held, addendum 130 item 2(c); the NCAA re-match comes by it, 130 item 3(b)) is never taken by the ingest
    beside it. Run 1 stores 26OCT16FLATEX refused (the game not yet stored); a ruling places it on the game; run 2
    lists 26OCT17FLATEX, placed by date on the same sides: it is stored refused under the matcher's claims rule, the
    ruled rows are not moved, and no side of the game carries two rows."""
    from datetime import date
    seed({}, code="NCAA", sport="NFL")                                      # the competition, no game yet
    ncaa_go(Fake(settled=ncaa(N16) + ncaa(N17)), until=date(2026, 10, 16))
    assert all(r["match_id"] is None and r["notes"].startswith("refused by the matcher: ") for r in rows().values())
    seed({NG: ("Florida Gators", "Texas Longhorns", NK, "finished")}, code="NCAA", sport="NFL")
    for sfx in ("FLA", "TEX"):
        res, _ = place(f"{N16}-{sfx}", NG)
        assert res["written"]
    before = rows()
    run, out = ncaa_go(Fake(settled=ncaa(N16) + ncaa(N17)), since=date(2026, 10, 17))
    got = rows()
    assert {k: v for k, v in _claims().items() if len(v) > 1} == {}
    for sfx, side in (("FLA", "AWAY"), ("TEX", "HOME")):
        assert (got[f"{N17}-{sfx}"]["match_id"], got[f"{N17}-{sfx}"]["side"]) == (None, None)
        assert got[f"{N17}-{sfx}"]["notes"].startswith(f"refused by the matcher: {km.TWO_CLAIMS}")
        assert got[f"{N16}-{sfx}"] == before[f"{N16}-{sfx}"]
        assert (got[f"{N16}-{sfx}"]["match_id"], got[f"{N16}-{sfx}"]["side"]) == (NG, side)
    assert run.refused == {km.TWO_CLAIMS: 2}
    assert f"  ✗ match {NG} AWAY: stored on {N16}-FLA (nothing already placed is moved); {N17}-FLA claims it too: " \
           "refused" in out


def test_a_date_only_stored_row_listed_again_still_refuses_its_side(db):
    """The stored row read as stored (addendum 132 item 3(b)) keeps a date-only series as main has it where the two
    agree: run 2 lists both twins (no window), the stored day-off twin 26OCT16FLATEX on the Saturday game's sides, so
    the own-date event 26OCT17FLATEX, placed by date there, is refused (main refused it by the twin's date placement,
    the same game) and the stored twin is not moved."""
    from datetime import date
    seed({NG: ("Florida Gators", "Texas Longhorns", NK, "finished")}, code="NCAA", sport="NFL")
    ncaa_go(Fake(settled=ncaa(N16) + ncaa(N17)), until=date(2026, 10, 16))
    before = rows()
    run, out = ncaa_go(Fake(settled=ncaa(N16) + ncaa(N17)))
    got = rows()
    assert {k: v for k, v in _claims().items() if len(v) > 1} == {}
    for sfx in ("FLA", "TEX"):
        assert got[f"{N16}-{sfx}"] == before[f"{N16}-{sfx}"]
        assert (got[f"{N17}-{sfx}"]["match_id"], got[f"{N17}-{sfx}"]["side"]) == (None, None)
        assert got[f"{N17}-{sfx}"]["notes"].startswith(f"refused by the matcher: {km.TWO_CLAIMS}")
    assert run.refused == {km.TWO_CLAIMS: 2} and run.already == 2


# ---- a refused stored row keeps its date claim (addendum 134 item 3: 132 item 3(b) is option (ii)) ------------------
# "only a stored row that HAS a placement enters the claims rule by its stored (match_id, side); a refused stored row
# keeps its date claim in the across-events rule, as on main. R1, R2 and R6 come in as regression tests." Read as
# worded (option (i)), a refused stored row claimed nothing, and each of these runs turned a refusal into a placement.

SETTLED17B = event(E17B, "no", "2026-10-18T03:30:00Z", "2026-10-18T03:35:00Z")


def _refused_two_claims(r):
    return (r["match_id"], r["side"]) == (None, None) and r["notes"].startswith(f"refused by the matcher: "
                                                                                f"{km.TWO_CLAIMS}")


def test_r1_a_cleared_held_row_beside_a_refused_stored_claimant_stays_refused(alcs):
    """R1, no failure needed. Run 1 holds 26OCT172000TBCLE (26OCT161800TBCLE listed open). Run 2: the hold clears, and
    it and the new 26OCT172010TBCLE both claim 50550 by date: both refused, the held row left as stored. Run 3, the same
    lists and nothing changed: the stored, refused 26OCT172010TBCLE still claims 50550 by its date, so the held row is
    refused again and nothing is written (as worded, run 3 placed the held row on 50550 alone)."""
    redate(G5, datetime(2026, 10, 17, 0, 0))                      # 26OCT161800TBCLE in step on 10-16
    go(Fake(settled=SETTLED15 + SETTLED17, opened=OPEN16))
    assert all(kh.is_held(r["match_id"], r["notes"]) for t, r in rows().items() if t.startswith(f"{E17}-"))
    lists = SETTLED15 + SETTLED16 + SETTLED17 + SETTLED17B
    run2, _ = go(Fake(settled=lists), now=datetime(2026, 10, 20, 12, 0))
    after2 = rows()
    for sfx in ("TB", "CLE"):
        assert kh.is_held(after2[f"{E17}-{sfx}"]["match_id"], after2[f"{E17}-{sfx}"]["notes"])
        assert _refused_two_claims(after2[f"{E17B}-{sfx}"])
    assert sorted(run2.held_refused) == [(f"{E17}-CLE", km.TWO_CLAIMS), (f"{E17}-TB", km.TWO_CLAIMS)]
    fake3 = Fake(settled=lists)
    run3, _ = go(fake3, now=datetime(2026, 10, 21, 12, 0))
    assert rows() == after2 and run3.replaced == [] and not fake3.candle_calls()
    assert sorted(run3.held_refused) == [(f"{E17}-CLE", km.TWO_CLAIMS), (f"{E17}-TB", km.TWO_CLAIMS)]
    assert {k: v for k, v in _claims().items() if len(v) > 1} == {}


def test_r2_a_leg_left_by_a_failed_candle_call_is_refused_on_the_next_run(alcs):
    """R2. Run 1: 26OCT172000TBCLE and 26OCT172010TBCLE both claim 50550: all four legs refused, and the TB leg of the
    second event is not stored (its candle call answers 503; the next run asks again). Run 2, no failure: that leg is
    refused beside its stored claimant, as run 1 refused it (as worded, it was placed on 50550 AWAY alone, half an
    event)."""
    lists = SETTLED17 + SETTLED17B
    go(Fake(settled=lists, fail={f"{E17B}-TB": 503}))
    after1 = rows()
    assert f"{E17B}-TB" not in after1
    assert all(_refused_two_claims(after1[t]) for t in (f"{E17}-TB", f"{E17}-CLE", f"{E17B}-CLE"))
    run2, _ = go(Fake(settled=lists), now=datetime(2026, 10, 20, 12, 0))
    got = rows()
    assert _refused_two_claims(got[f"{E17B}-TB"])
    assert {t: r for t, r in got.items() if t != f"{E17B}-TB"} == after1
    assert run2.refused == {km.TWO_CLAIMS: 1} and len(run2.rows) == 1
    assert _claims() == {}                                        # no leg of either event placed


def test_r6_a_day_off_twin_listed_beside_its_refused_own_date_event_is_refused(db):
    """R6, NCAA, no cap and no failure. Run 1 (--since 2026-10-17) lists the own-date event 26OCT17FLATEX before the
    Saturday game is synced: stored refused, no game. The game is synced; run 2 (no window) lists the day-off twin
    26OCT16FLATEX new beside it. The stored own-date event, refused, still claims the Saturday game by its date, so the
    twin is refused, as main refuses it (as worded, the twin was placed on the Saturday game: the misplacement addendum
    130 item 3(b) names)."""
    seed({}, code="NCAA", sport="NFL")                                      # the competition, no game yet
    ncaa_go(Fake(settled=ncaa(N16) + ncaa(N17)), since=date(2026, 10, 17))
    after1 = rows()
    assert sorted(after1) == [f"{N17}-FLA", f"{N17}-TEX"]
    assert all(r["match_id"] is None and r["notes"].startswith("refused by the matcher: ") for r in after1.values())
    seed({NG: ("Florida Gators", "Texas Longhorns", NK, "finished")}, code="NCAA", sport="NFL")
    run2, _ = ncaa_go(Fake(settled=ncaa(N16) + ncaa(N17)))
    got = rows()
    for sfx in ("FLA", "TEX"):
        assert _refused_two_claims(got[f"{N16}-{sfx}"])
        assert got[f"{N17}-{sfx}"] == after1[f"{N17}-{sfx}"]
    assert run2.refused == {km.TWO_CLAIMS: 2} and run2.already == 2
    assert _claims() == {}                                        # neither twin placed


def test_a_row_refused_for_another_reason_is_not_read_again(alcs):
    """Only a held row is the exception: 26OCT161800TBCLE, refused "no game of the pair on the ticker's date", stays
    so although 50548 is now dated 10-16 and the matcher would place it there."""
    go(Fake(settled=SETTLED15 + SETTLED16))
    before = rows()
    redate(G5, datetime(2026, 10, 17, 0, 0))
    fake = Fake(settled=SETTLED15 + SETTLED16)
    run, _ = go(fake)
    assert rows() == before and run.already == 4 and not fake.candle_calls()


def test_the_open_list_cut_short_stores_nothing(alcs):
    """The hold cannot be read on half the open list: a cut there stores nothing, as for the other lists."""
    class Cut(Fake):
        def _get(self, path, params=None):
            if path == "markets" and (params or {}).get("status") == "open":
                self.calls.append((path, dict(params)))
                return {"markets": [], "cursor": "again"} if not (params or {}).get("cursor") else \
                    {"markets": [], "cursor": "again"}
            return super()._get(path, params)
    run, out = go(Cut(settled=SETTLED15 + SETTLED16 + SETTLED17))
    assert rows() == {} and run.rows == []
    assert any("open: the cursor 'again' came back on page 2 of markets" in ln for ln in out)


# ---- place-held -----------------------------------------------------------------------------------------------------

def _monday(alcs):
    """The Monday pull written: 26OCT151800TBCLE on Game 3, 26OCT161800TBCLE refused, 26OCT172000TBCLE held."""
    go(Fake(settled=SETTLED15 + SETTLED16 + SETTLED17))
    return rows()


def place(ticker, mid, *, fake=None, ruling=RULING, **kw):
    out = []
    res = kh.place_held(ticker, mid, ruling, adapter=fake or Fake(), echo=out.append,
                        now=datetime(2026, 10, 18, 15, 0), **kw)
    return res, out


def test_place_held_places_26oct161800_on_50550_and_reads_its_candles_then(alcs):
    """Addendum 130 item 2(c)'s first two uses: 26OCT161800TBCLE-TB and -CLE -> 50550 (TB away, CLE home). The ruling
    is appended to the notes; the candles are read on 50550's kickoff by the ingest's own call."""
    before = _monday(alcs)
    fake = Fake(candles={f"{E16}-TB": candles_at(K4, "0.47", "0.48")})
    res, out = place(f"{E16}-TB", G4, fake=fake)
    place(f"{E16}-CLE", G4, fake=Fake())
    got = rows()
    tb, cle = got[f"{E16}-TB"], got[f"{E16}-CLE"]
    assert (tb["match_id"], tb["side"], cle["match_id"], cle["side"]) == (G4, "AWAY", G4, "HOME")
    assert tb["notes"] == (f"{before[f'{E16}-TB']['notes']}; placed by ruling: {RULING}; candles read at placement on "
                           f"match {G4}'s kickoff")
    assert (tb["last_ts"], tb["last_bid"], tb["last_ask"], tb["last_mid"]) == (K4, 0.47, 0.48, pytest.approx(0.475))
    assert cle["last_ts"] is None and cle["notes"].endswith("; no two-sided candle at or before kickoff")
    assert fake.candle_calls() == {f"{E16}-TB": {"start_ts": _ts(datetime(2026, 10, 17, 18, 8)),
                                                 "end_ts": _ts(datetime(2026, 10, 18, 3, 18)), "period_interval": 1}}
    assert [p for p, _ in fake.calls] == [f"series/{S}/markets/{E16}-TB/candlesticks"]
    assert tb["fetched_at"] == datetime(2026, 10, 18, 15, 0) and res["written"]
    assert {t: r for t, r in got.items() if not t.startswith(E16)} == {t: r for t, r in before.items()
                                                                       if not t.startswith(E16)}
    assert out[0] == f"kalshi-history place-held {E16}-TB → match {G4} · writes this one row of " \
                     f"kalshi_settled_markets · ruling: {RULING}"
    assert out[1].startswith(f"  before: {E16}-TB · live · match - - · result yes · settled 2026-10-18 03:20:00Z")
    assert out[2] == (f"  match {G4}: {TB} at {CLE} · kickoff 2026-10-18 00:08Z (2026-10-17 20:08 ET) · finished · the "
                      "event's names Tampa Bay / Cleveland fit it one each: Tampa Bay is AWAY")
    assert out[-2].startswith(f"  after:  {E16}-TB · live · match {G4} AWAY · result yes")
    assert out[-1] == f"  ✓ placed: {E16}-TB on match {G4} AWAY (one row written)"


def test_the_later_run_holds_26oct172000_still_and_the_third_use_places_it_on_50548(alcs):
    """The words settle the ordering: placing 26OCT161800TBCLE by ruling does not put it in step on its own date, so
    26OCT172000TBCLE stays held by the ingest; the third use (addendum 130 item 2(c)) places it on 50548."""
    _monday(alcs)
    place(f"{E16}-TB", G4)
    place(f"{E16}-CLE", G4)
    run, out = go(Fake(settled=SETTLED15 + SETTLED16 + SETTLED17), now=datetime(2026, 10, 20, 12, 0))
    assert run.held_still == 2 and not run.replaced
    assert f"  ⏸ {E17}: {hold(E16, 'out of step')} (no game of its two teams on its date 2026-10-16); held, not " \
           f"placed by date: {E17}-CLE, {E17}-TB" in out
    place(f"{E17}-TB", G5)
    place(f"{E17}-CLE", G5)
    got = rows()
    assert (got[f"{E17}-TB"]["match_id"], got[f"{E17}-TB"]["side"]) == (G5, "AWAY")
    assert (got[f"{E17}-CLE"]["match_id"], got[f"{E17}-CLE"]["side"]) == (G5, "HOME")
    assert got[f"{E17}-TB"]["notes"].startswith(f"{hold(E16, 'out of step')}; {kh.HOLD_NO_CANDLES}; placed by ruling: ")
    run, _ = go(Fake(settled=SETTLED15 + SETTLED16 + SETTLED17), now=datetime(2026, 10, 21, 12, 0))
    assert rows() == got and run.already == 6


CANDLES16 = f"series/{S}/markets/{E16}-TB/candlesticks"


def refused_for_now(why, retries=0):
    """place-held's one line on a candle call that fails for now (addendum 132 item 3(a))."""
    return (f"REFUSED: the candle call {CANDLES16} failed ({why}; 429 retries: {retries}): nothing is written (the "
            "quote lands with the placement or the placement does not land, addendum 132 item 3(a)); run it again")


@pytest.mark.parametrize("fail, why, n", [
    (503, "status 503", 1),                                                            # a 5xx
    (408, "status 408", 1),                                                            # a 408
    (requests.ConnectionError("connection reset"), "ConnectionError: connection reset", 1),     # a transport error
    (429, "status 429", 3),                                                            # a third 429
    ("no list", "no 'candlesticks' list", 1),                                          # an answer with no list
], ids=["5xx", "408", "transport", "third-429", "no-list"])
def test_a_candle_call_that_fails_for_now_writes_nothing(alcs, waits, fail, why, n):
    """Addendum 132 item 3(a): "`place-held` after a candle call that fails (a 5xx, a 408, a transport error, a third
    429, an answer with no list): WRITE NOTHING, say why, exit 2 — the operator re-runs. ... "fetches its candles then"
    means the quote lands with the placement or the placement does not land. (The ingest's own rule for the same
    failures is store-nothing; the command follows it.)" The row stays exactly as stored, and the refusal names the
    call and the failure; a dry run refuses the same."""
    before = _monday(alcs)
    fake = Fake(fail={f"{E16}-TB": fail})
    with pytest.raises(ValueError) as e:
        place(f"{E16}-TB", G4, fake=fake)
    assert str(e.value) == refused_for_now(why, n - 1)
    assert rows() == before and [p for p, _ in fake.calls] == [CANDLES16] * n and waits == [2, 5][:n - 1]
    with pytest.raises(ValueError) as dry:
        place(f"{E16}-TB", G4, fake=Fake(fail={f"{E16}-TB": fail}), dry_run=True)
    assert str(dry.value) == str(e.value) and rows() == before


def test_a_candle_call_refused_for_good_keeps_the_placement_with_no_quote(alcs):
    """Not in 132 item 3(a)'s list: a 4xx other than 408 / 429 (the exchange refuses for good, _refused_for_good). The
    ingest stores such a market with a null quote and the status in notes; place-held keeps that, as built."""
    _monday(alcs)
    res, out = place(f"{E16}-TB", G4, fake=Fake(fail={f"{E16}-TB": 404}))
    r = rows()[f"{E16}-TB"]
    assert (r["match_id"], r["side"], r["last_ts"], r["last_bid"]) == (G4, "AWAY", None, None) and res["written"]
    assert r["notes"].endswith(f"; placed by ruling: {RULING}; candle call failed at placement (status 404): no quote; "
                               "the placement stands")
    assert any(ln.startswith(f"  ✗ candles: {CANDLES16} failed (status 404): the placement stands with no quote")
               for ln in out)


def test_a_429_at_placement_is_asked_again(alcs, waits):
    _monday(alcs)

    class Once429(Fake):
        hit = False

        def _get(self, path, params=None):
            if path.endswith("/candlesticks") and not self.hit:
                self.hit = True
                resp = requests.Response()
                resp.status_code = 429
                raise requests.HTTPError(response=resp)
            return super()._get(path, params)
    res, out = place(f"{E16}-TB", G4, fake=Once429(candles={f"{E16}-TB": candles_at(K4)}))
    assert waits == [2] and rows()[f"{E16}-TB"]["last_bid"] == 0.45
    assert any("429 retries: 1" in ln for ln in out)


def test_place_held_dry_run_writes_nothing_and_skips_the_guard(alcs):
    from src.db.database import get_engine
    _monday(alcs)
    eng = get_engine()

    def counts():
        with eng.connect() as c:
            return {t: c.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar() for t in inspect(eng).get_table_names()}
    before, n0 = rows(), counts()
    guarded = []
    res, out = place(f"{E16}-TB", G4, dry_run=True, guard=lambda: guarded.append(1),
                     fake=Fake(candles={f"{E16}-TB": candles_at(K4)}))
    assert rows() == before and counts() == n0 and not guarded and not res["written"]
    assert res["after"]["match_id"] == G4 and res["after"]["last_bid"] == 0.45
    assert out[0].endswith(f"DRY RUN: nothing is written · ruling: {RULING}") and out[-1] == "  DRY RUN: nothing written"


def test_the_guard_runs_once_every_refusal_is_read_and_before_the_candle_call(alcs):
    _monday(alcs)
    order = []

    class Spy(Fake):
        def _get(self, path, params=None):
            order.append("call")
            return super()._get(path, params)
    place(f"{E16}-TB", G4, fake=Spy(), guard=lambda: order.append("guard"))
    assert order == ["guard", "call"]
    with pytest.raises(ValueError):
        place(f"{E16}-TB", G4, guard=lambda: order.append("guard again"))       # already placed: refused first
    assert "guard again" not in order


@pytest.mark.parametrize("ticker, mid, ruling, msg", [
    (f"{E16}-TB", G4, "   ", "REFUSED: --ruling is empty"),
    (f"{S}-26OCT201600TBCLE-TB", G4, RULING, f"REFUSED: no row of kalshi_settled_markets has ticker '{S}-26OCT201600TBCLE-TB'"),
    (f"{E15}-TB", G3, RULING, f"REFUSED: {E15}-TB is already placed on match {G3} AWAY: nothing already placed is moved"),
    (f"{E16}-TB", 99999, RULING, "REFUSED: no match 99999"),
])
def test_place_held_refuses(alcs, ticker, mid, ruling, msg):
    before = _monday(alcs)
    with pytest.raises(ValueError, match="^" + msg.replace("(", r"\(").replace(")", r"\)")):
        place(ticker, mid, ruling=ruling)
    assert rows() == before


def test_place_held_refuses_a_row_with_no_hold_or_refusal_note(alcs):
    from src.db.database import session_scope
    from src.db.schema import KalshiSettledMarket
    _monday(alcs)
    with session_scope() as s:
        s.add(KalshiSettledMarket(ticker=f"{S}-26OCT141800TBCLE-TB", event_ticker=f"{S}-26OCT141800TBCLE", series=S,
                                  yes_sub_title="Tampa Bay", source="live", fetched_at=NOW,
                                  notes="result as read: 'scalar'"))
    with pytest.raises(ValueError, match="carries no identity hold and no refusal in its notes"):
        place(f"{S}-26OCT141800TBCLE-TB", G3)


def test_place_held_refuses_a_match_of_another_competition_or_other_teams(alcs):
    seed({777: (TB, CLE, K4, "finished")}, code="ZOT", sport="MLB")
    seed({778: ("New York Yankees", "Boston Red Sox", K4, "finished")})
    before = _monday(alcs)
    with pytest.raises(ValueError, match="match 777 is not a game of KXMLBGAME's own competition"):
        place(f"{E16}-TB", 777)
    with pytest.raises(ValueError, match=r"match 778's teams \(New York Yankees at Boston Red Sox\) are not the event's "
                                         r"two names \(Tampa Bay, Cleveland\) one each"):
        place(f"{E16}-TB", 778)
    assert rows() == before


def test_place_held_refuses_when_the_side_cannot_be_told(alcs):
    """The names fit both teams the same way round and the other (no word tells them apart): the side is not told."""
    from src.db.database import session_scope
    from src.db.schema import KalshiSettledMarket
    seed({779: ("Alpha Owls", "Alpha Bears", K4, "finished")})
    ev = f"{S}-26OCT172000ALPALP"
    with session_scope() as s:
        for sfx, nm in (("ALX", "Alpha X"), ("ALY", "Alpha Y")):
            s.add(KalshiSettledMarket(ticker=f"{ev}-{sfx}", event_ticker=ev, series=S, yes_sub_title=nm, source="live",
                                      fetched_at=NOW, notes=f"refused by the matcher: {km.SIDE_TIE}"))
    assert km.fit(("Alpha X", "Alpha Y"), "Alpha Bears", "Alpha Owls")[1] is None
    with pytest.raises(ValueError, match="cannot tell home from away on match 779"):
        place(f"{ev}-ALX", 779)


def test_place_held_refuses_a_side_another_row_holds(alcs):
    _monday(alcs)
    place(f"{E16}-TB", G4)
    with pytest.raises(ValueError, match=f"REFUSED: match {G4} AWAY is already held by {E16}-TB"):
        place(f"{E17}-TB", G4)


def test_place_held_reads_the_side_again_in_its_write(alcs):
    """Codex review on #598: the side check ran before the candle call, and the write re-checked only the ticker. Here
    another row takes 50550 AWAY while place-held reads the candles (a second place-held, or a history run): the write
    reads the side again in its own transaction and refuses, and nothing is written."""
    from src.db.database import session_scope
    from src.db.schema import KalshiSettledMarket
    before = _monday(alcs)

    class Race(Fake):
        def _get(self, path, params=None):
            if path.endswith(f"/{E16}-TB/candlesticks"):
                with session_scope() as s:
                    s.add(KalshiSettledMarket(ticker=f"{S}-26OCT171900TBCLE-TB", event_ticker=f"{S}-26OCT171900TBCLE",
                                              series=S, side="AWAY", match_id=G4, yes_sub_title="Tampa Bay",
                                              source="live", fetched_at=NOW, notes="placed by ruling: test"))
            return super()._get(path, params)
    with pytest.raises(ValueError, match=f"REFUSED: match {G4} AWAY was taken by {S}-26OCT171900TBCLE-TB before the "
                                         "write: two settled markets are never stored on one side of one game; nothing "
                                         "is written"):
        place(f"{E16}-TB", G4, fake=Race())
    assert rows()[f"{E16}-TB"] == before[f"{E16}-TB"]
    assert {k: v for k, v in _claims().items() if len(v) > 1} == {}


def test_place_held_reads_the_held_row_s_sides_on_the_match_s_own_home_and_away(alcs):
    """The side is the market's yes team against the match's home and away: on a match stored the other way round
    (Cleveland away), Tampa Bay's leg is HOME."""
    seed({780: (CLE, TB, K5, "scheduled")})
    _monday(alcs)
    place(f"{E17}-TB", 780)
    place(f"{E17}-CLE", 780)
    got = rows()
    assert (got[f"{E17}-TB"]["side"], got[f"{E17}-CLE"]["side"]) == ("HOME", "AWAY")


# ---- the command ----------------------------------------------------------------------------------------------------

def _backup(src, dst):
    with sqlite3.connect(src) as a, sqlite3.connect(dst) as b:
        a.backup(b)
    return dst


def test_the_command_needs_a_backup_to_write_and_takes_one(alcs, tmp_path, monkeypatch):
    import cli
    _monday(alcs)
    fake = Fake(candles={f"{E16}-TB": candles_at(K4)})
    monkeypatch.setattr(KalshiAdapter, "_get", lambda self, path, params=None: fake._get(path, params))
    args = ["kalshi-history", "place-held", "--ticker", f"{E16}-TB", "--match-id", str(G4), "--ruling", RULING]
    res = CliRunner().invoke(cli.cli, args)
    assert res.exit_code == 2 and "REFUSED [check: --backup given]" in res.output and rows()[f"{E16}-TB"]["match_id"] is None
    dry = CliRunner().invoke(cli.cli, args + ["--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert "DRY RUN: nothing written" in dry.output and rows()[f"{E16}-TB"]["match_id"] is None
    stale = _backup(str(alcs), str(tmp_path / "stale.backup"))
    from src.db.database import session_scope
    from src.db.schema import KalshiSettledMarket
    with session_scope() as s:                                       # a write after the backup: its count is behind
        s.add(KalshiSettledMarket(ticker=f"{S}-26OCT141800TBCLE-TB", series=S, source="live", fetched_at=NOW))
    res = CliRunner().invoke(cli.cli, args + ["--backup", stale])
    assert res.exit_code == 2 and "kalshi_settled_markets count = live" in res.output
    assert rows()[f"{E16}-TB"]["match_id"] is None
    good = _backup(str(alcs), str(tmp_path / "good.backup"))
    res = CliRunner().invoke(cli.cli, args + ["--backup", good])
    assert res.exit_code == 0, res.output
    assert "backup verified:" in res.output and f"✓ placed: {E16}-TB on match {G4} AWAY" in res.output
    assert rows()[f"{E16}-TB"]["match_id"] == G4
    again = CliRunner().invoke(cli.cli, args + ["--backup", good])
    assert again.exit_code == 2 and "is already placed on match" in again.output


def test_the_command_exits_2_on_a_candle_call_that_fails_for_now(alcs, tmp_path, monkeypatch):
    """132 item 3(a) at the command: a 5xx on the candle call, dry or with a verified backup, ends in the one REFUSED
    line and exit 2, and the row is as stored: the operator re-runs."""
    import cli
    before = _monday(alcs)
    fake = Fake(fail={f"{E16}-TB": 503})
    monkeypatch.setattr(KalshiAdapter, "_get", lambda self, path, params=None: fake._get(path, params))
    args = ["kalshi-history", "place-held", "--ticker", f"{E16}-TB", "--match-id", str(G4), "--ruling", RULING]
    good = _backup(str(alcs), str(tmp_path / "good.backup"))
    for extra in (["--dry-run"], ["--backup", good]):
        res = CliRunner().invoke(cli.cli, args + extra)
        assert res.exit_code == 2, res.output
        assert res.output.splitlines()[-1] == refused_for_now("status 503")
        assert rows() == before


def test_the_pull_keeps_its_invocation_and_its_options_stay_off_the_subcommand(alcs, monkeypatch):
    import cli
    fake = Fake(settled=SETTLED15 + SETTLED16 + SETTLED17)
    monkeypatch.setattr(KalshiAdapter, "_get", lambda self, path, params=None: fake._get(path, params))
    res = CliRunner().invoke(cli.cli, ["kalshi-history", "--series", S, "--dry-run", "--since", "2026-10-15",
                                       "--max-calls", "50"])
    assert res.exit_code == 0, res.output
    assert f"kalshi-history {S} (MLB) · DRY RUN: nothing is written · max calls 50" in res.output
    assert f"⏸ {E17}: {hold(E16, 'out of step')}" in res.output and rows() == {}
    bad = CliRunner().invoke(cli.cli, ["kalshi-history", "--series", S, "place-held", "--ticker", "X",
                                       "--match-id", "1", "--ruling", RULING])
    assert bad.exit_code == 2 and "--series belong to the pull" in bad.output
    none = CliRunner().invoke(cli.cli, ["kalshi-history"])
    assert none.exit_code == 2 and "Missing option '--series'" in none.output


def test_the_matcher_is_not_changed():
    """Gate-adjacent (addendum 127 item 3(c): "the shared matcher untouched"): the hold reads the matcher's own
    out-of-step rule; kalshi_match.py names no hold."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "src" / "ingestion" / "kalshi_match.py").read_text()
    assert "identity hold" not in src and "place_held" not in src
