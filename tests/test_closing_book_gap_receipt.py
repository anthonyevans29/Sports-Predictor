"""Addendum 532 item 4, ruled by 534 item 3 (Refs #348): the closing book-gap receipt, read-only.

A throwaway SQLite copy under tmp_path (never data/), built through the ORM with the unmapped
odds_snapshots.source_updated_at added by ALTER TABLE (tests/test_pl_closing_book_age_receipt.py's pattern), and
SOCCER and NFL closing pages as a closing run writes them. Every value is synthetic. The desk blocks carry sentinel
units, orders, exec costs and a unit label that must never reach the console."""
import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "closing_book_gap_receipt.py"
_spec = importlib.util.spec_from_file_location("closing_book_gap_receipt", SCRIPT)
rc = importlib.util.module_from_spec(_spec)
sys.modules["closing_book_gap_receipt"] = rc
_spec.loader.exec_module(rc)


def _dt(v):
    return datetime.fromisoformat(v)


S3 = ("HOME", "DRAW", "AWAY")
S2 = ("HOME", "AWAY")
# SOCCER: the page of 2026-11-21 15:00Z, exported 14:27:03.123456Z
SD = "2026-11-21T"
S_EXP = SD + "14:27:03.123456Z"
S_EXP_DT = _dt(SD + "14:27:03.123456")
F3 = (0.452311, 0.271502, 0.276187)        # page fair 0.4523 / 0.2715 / 0.2762
K3 = {"HOME": 0.5, "DRAW": 0.25, "AWAY": 0.25}
# NFL: the page of 2026-11-22 18:00Z, exported 17:55:00.5Z
ND = "2026-11-22T"
N_EXP = ND + "17:55:00.500000Z"
F2 = (0.600012, 0.399988)                  # page fair 0.6000 / 0.4000

SENTINELS = ("777.77", "4242", "31337", "9999", "SecretBook", "88.88", "6161")

# THE NFL PREMISE (the pre-PR review's P1): three books at different overrounds in one fetch. The page's fair is
# close_1x2's (de-vigged per complete book, then averaged; nfl_predict.py:268-275), the snapshot's is
# sync_odds_nfl's (the mean implied per selection over every offer, over their sum; service.py:3019-3036).
BOOKS = {"A": (1.50, 2.60), "B": (1.55, 2.40), "C": (1.45, 2.85)}


def _nfl_page_fair():
    from types import SimpleNamespace as NS

    from src.walters.close import BINARY, close_1x2
    t = datetime.fromisoformat("2026-11-22T17:50:00")
    rows = [NS(market="1X2", selection=sel, bookmaker=bk, price_decimal=px[i], captured_at=t, line=None)
            for bk, px in BOOKS.items() for i, sel in enumerate(("HOME", "AWAY"))]
    f = close_1x2(rows, None, BINARY)["fair"]
    return (f["HOME"], f["AWAY"])


def _nfl_pooled():
    from src.walters.value import MarketSnapshot
    by = {sel: [(bk, px[i]) for bk, px in BOOKS.items()] for i, sel in enumerate(("HOME", "AWAY"))}
    imp = MarketSnapshot(market="1X2", by_selection=by).average_implied()
    over = sum(imp.values())
    return (imp["HOME"] / over, imp["AWAY"] / over)


PAGE206, POOLED206 = _nfl_page_fair(), _nfl_pooled()

# id: (family, home, away, kickoff, [(captured_at, values, stamp)])
GAMES = {
    90: ("SOCCER", "Leeds", "Burnley", "2026-11-14T15:00:00", [("2026-11-14T14:20:00", F3, None)]),
    100: ("SOCCER", "Chelsea", "Arsenal", SD + "15:00:00", [(SD + "14:25:00", F3, SD + "14:20:00")]),
    101: ("SOCCER", "Liverpool", "Everton", SD + "15:00:00", [(SD + "14:25:00", F3, SD + "10:50:00")]),
    102: ("SOCCER", "Tottenham", "Fulham", SD + "15:00:00", [(SD + "14:25:00", F3, "2026-11-20T10:00:00")]),
    103: ("SOCCER", "Wolves", "Brentford", SD + "15:00:00", [(SD + "14:25:00", F3, None)]),
    104: ("SOCCER", "Aston Villa", "Newcastle", SD + "15:00:00", [(SD + "14:25:00", F3, SD + "14:30:00")]),
    105: ("SOCCER", "Brighton", "Bournemouth", SD + "15:00:00", [(SD + "14:25:00", F3, SD + "14:20:00")]),
    106: ("SOCCER", "West Ham", "Sunderland", SD + "15:00:00", [(SD + "14:25:00", F3, SD + "14:20:00")]),
    107: ("SOCCER", "Everton B", "Fulham B", SD + "15:00:00", [(SD + "14:25:00", (0.5, 0.3, 0.2), SD + "14:20:00")]),
    108: ("SOCCER", "Crystal Palace", "Brentford B", SD + "15:00:00",
          [(SD + "14:25:00", F3, "2026-11-20T20:00:00")]),
    109: ("SOCCER", "Nottingham Forest", "Newcastle B", SD + "15:00:00", [(SD + "14:25:00", F3, SD + "12:00:00")]),
    110: ("SOCCER", "Manchester City", "Manchester United", SD + "12:30:00", [(SD + "11:20:00", F3, SD + "11:00:00")]),
    200: ("NFL", "Bears", "Packers", ND + "18:00:00", [(ND + "17:50:00", F2, ND + "05:00:00")]),
    201: ("NFL", "Lions", "Vikings", ND + "18:00:00", [(ND + "17:50:00", F2, ND + "15:00:00")]),
    202: ("NFL", "Jets", "Bills", ND + "18:00:00", [(ND + "17:50:00", F2, ND + "15:00:00")]),
    203: ("NFL", "Giants", "Eagles", ND + "18:00:00", [(ND + "17:50:00", F2, ND + "15:00:00")]),
    204: ("NFL", "Rams", "Seahawks", ND + "18:00:00", [(ND + "17:50:00", F2, ND + "09:00:00")]),
    205: ("NFL", "Chiefs", "Raiders", ND + "18:00:00", [(ND + "17:50:00", F2, ND + "15:00:00")]),
    206: ("NFL", "Broncos", "Chargers", ND + "18:00:00",
          [(ND + "16:50:00", PAGE206, ND + "05:00:00"), (ND + "17:50:00", POOLED206, ND + "15:00:00")]),
}


def build_db(path: Path, stamp: bool = True) -> None:
    from src.db.schema import Base, Competition, Match, MatchStatus, OddsSnapshot, Sport, Team
    eng = create_engine("sqlite:///{}".format(path))
    Base.metadata.create_all(eng)
    if stamp:
        with eng.begin() as c:
            c.execute(text("ALTER TABLE odds_snapshots ADD COLUMN source_updated_at DATETIME"))
    with Session(eng) as s:
        comps = {"SOCCER": Competition(sport=Sport.SOCCER, code="PL", name="Premier League", area="England",
                                       type="LEAGUE"),
                 "NFL": Competition(sport=Sport.NFL, code="NFL", name="NFL", area="USA", type="LEAGUE")}
        s.add_all(comps.values())
        s.flush()
        teams = {}
        for mid, (fam, h, a, ko, snaps) in GAMES.items():
            sport = Sport.SOCCER if fam == "SOCCER" else Sport.NFL
            for n in (h, a):
                if n not in teams:
                    teams[n] = Team(sport=sport, name=n)
                    s.add(teams[n])
            s.flush()
            s.add(Match(id=mid, sport=sport, competition_id=comps[fam].id,
                        season="2026/27" if fam == "SOCCER" else "2026", utc_date=_dt(ko),
                        status=MatchStatus.SCHEDULED, home_team_id=teams[h].id, away_team_id=teams[a].id))
            s.flush()
            legs = S3 if fam == "SOCCER" else S2
            src = "api_football" if fam == "SOCCER" else "api_american_football"
            for at, vals, st in snaps:
                for sel, v in zip(legs, vals):
                    o = OddsSnapshot(match_id=mid, market="1X2", selection=sel, devig_prob=v, n_books=5,
                                     captured_at=_dt(at), source=src)
                    s.add(o)
                    s.flush()
                    if stamp and st is not None:
                        s.execute(text("UPDATE odds_snapshots SET source_updated_at = :t WHERE id = :i"),
                                  {"t": _dt(st).strftime("%Y-%m-%d %H:%M:%S.%f"), "i": o.id})
        # another source's book row and a kalshi row on 100: never read as the books' session
        s.add(OddsSnapshot(match_id=100, market="1X2", selection="HOME", devig_prob=0.9,
                           captured_at=_dt(SD + "14:26:00"), source="kalshi"))
        s.add(OddsSnapshot(match_id=200, market="1X2", selection="HOME", devig_prob=0.9,
                           captured_at=_dt(ND + "17:52:00"), source="api_football"))
        s.commit()
    eng.dispose()


def desk(call="PASS", pick="HOME", reference="books", market_ref=None):
    return {"call": call, "pick": pick, "reference": reference, "market_ref": market_ref, "units": 777.77,
            "shadow_units": 88.88, "edge_pp": 1.0, "model_p": 0.5,
            "order": {"contracts": 4242, "unit": "1u = $9999", "text": "BUY 4242"},
            "exec": {"cost": 31337, "contracts": 4242}, "ladder_exec": {"cost": 31337},
            "value_shadow": {"units": 777.77}, "market_only_hold": {"would_units": 777.77}}


def srow(mid, fair=F3, kalshi=K3, normalized=True, status=None, dk=None, comp="PL", season="2026/27"):
    _f, h, a, ko, _s = GAMES[mid]
    sels = {} if fair is None else {s: {"fair_prob": round(v, 4), "best_price": 6161.0,
                                        "best_bookmaker": "SecretBook"} for s, v in zip(S3, fair)}
    kal = None
    if status:
        kal = {"status": status, "events": []}
    elif kalshi is not None:
        kal = {"raw_yes_prob": dict(kalshi), "raw_sum": 1.0, "prob": dict(kalshi) if normalized else None,
               "normalized": normalized, "captured_at": SD + "14:26:00"}
    r = {"match_id": mid, "utc_date": ko, "competition": comp, "season": season, "home_team": h, "away_team": a,
         "market": {"selections": sels, "bookmaker_count": 5, **({"kalshi": kal} if kal else {})},
         "kalshi_bid": 6161, "kalshi_ask": 6161, "exec_cost_taker": 31337, "fee_order_contracts": 4242,
         "kalshi_legs": {"HOME": {"ticker": "T", "bid": 6161, "ask": 6161}}}
    if dk is not None:
        r["desk"] = dk
    return r


def nrow(mid, fair=F2, kalshi_prob=0.55, source="1X2", mismatched=False, dk=None, to_at=None):
    _f, h, a, ko, _s = GAMES[mid]
    r = {"match_id": mid, "utc_date": ko, "week": 12, "stage": "REGULAR", "home_team": h, "away_team": a,
         "market": {"bookmaker_count": 5, "fair_prob": {k: round(v, 4) for k, v in zip(S2, fair)},
                    "fair_source": source},
         "kalshi_prob": kalshi_prob, "kalshi_captured_at": ND + "17:54:00", "venue_gap_pp": 99.9,
         "kalshi_bid": 6161, "away_bid": 6161, "exec_cost_maker_away": 31337,
         "input_quality": {"book_odds": 5, **({"kalshi": "mismatched"} if mismatched else {})},
         "line_move": None if to_at is None else {"flag": None, "venues": {"book": {"to_at": to_at}}}}
    if dk is not None:
        r["desk"] = dk
    return r


def closing(folder: Path, start: str, exported, rows: list, fam="SOCCER", run_id=None):
    folder.mkdir(parents=True, exist_ok=True)
    st = _dt(start)
    doc = {"exported_at": exported, "git_sha": "c53a6a60c0ffee", "count": len(rows), "predictions": rows,
           "desk_meta": {"unit": {"label": "1u = $9999", "fraction": 0.01}},
           "closing": {"family": fam, "start": start + "Z", "run_id": run_id or "run-{:%m%d%H%M}".format(st),
                       "match_ids": [r["match_id"] for r in rows], "called_off": []}}
    p = folder / "closing_{}_{:%Y-%m-%dT%H%M}Z.json".format(fam, st)
    p.write_text(json.dumps(doc))
    return p


def soccer_page():
    return [srow(100, dk=desk("PLAY", "HOME", "books", 0.4523)),     # under 1 h; staked; market_ref agrees
            srow(101, dk=desk("LADDER", "DRAW", "books", 0.2715)),   # 3-6 h; the LADDER line
            srow(102, dk=desk("PASS")),                              # 24 h or more
            srow(103, dk=desk("PLAY", "AWAY", "books", 0.2762)),     # no stamp, gap kept
            srow(104, dk=desk("PASS")),                              # stamp after the export
            srow(105, normalized=False, dk=desk("PASS")),            # Kalshi not normalised: no gap
            srow(106, status="mismatched", dk=desk("PASS")),         # Kalshi mismatched: no gap
            srow(107, dk=desk("PLAY", "HOME", "books", 0.4523)),     # no stored session matches: gap apart
            srow(108, dk=desk("PLAY", "HOME", "books", 0.4000)),     # 12-24 h; market_ref differs
            srow(109),                                               # 2-3 h; no desk block
            srow(100, comp="ELC"), srow(100, season="2025/26")]      # another competition / season: not read


def nfl_page():
    return [nrow(200, dk=desk("PASS")),                                   # 12-24 h, gap 5.00
            nrow(201, dk=desk("PLAY", "AWAY", "kalshi_only", 0.45)),      # 2-3 h; reference not the books
            nrow(202, kalshi_prob=None, dk=desk("PASS")),                 # no Kalshi pair
            nrow(203, source="spread_derived", dk=desk("PASS")),          # fair not the 1X2 consensus
            nrow(204, dk=desk("PLAY", "AWAY", "books", 0.4), to_at=ND + "17:40:00"),   # 6-12 h; line_move differs
            nrow(205, mismatched=True, kalshi_prob=None, dk=desk("PASS")),
            # the pooled snapshot of the page's own fetch, unequal at 4 places; an EARLIER session that equals the
            # page is never taken (by capture time, NFL); line_move's to_at agrees
            nrow(206, fair=PAGE206, dk=desk("PASS"), to_at=ND + "17:50:00")]


def write_exports(ex: Path):
    closing(ex, "2026-11-14T15:00:00", "2026-11-14T14:27:00.000000Z", [srow(90, dk=desk("PLAY"))])   # before first
    closing(ex, SD + "15:00:00", S_EXP, soccer_page())
    # the same start, an EARLIER page kept in a dated folder: labelled, out
    closing(ex / "2026-11-21", SD + "15:00:00", SD + "14:00:00.000000Z", [srow(100, kalshi={"HOME": 0.9,
                                                                                            "DRAW": 0.05,
                                                                                            "AWAY": 0.05})],
            run_id="run-earlier")
    # a byte copy of the counted page in another dated folder: a COPY, never counted twice
    closing(ex / "2026-11-22", SD + "15:00:00", S_EXP, soccer_page())
    # a start whose two pages share one exported_at under two run ids: the latest cannot be told, none counts
    closing(ex, SD + "12:30:00", SD + "11:57:00.000000Z", [srow(110)], run_id="run-a")
    closing(ex / "2026-11-20", SD + "12:30:00", SD + "11:57:00.000000Z", [srow(110)], run_id="run-b")
    closing(ex, ND + "18:00:00", N_EXP, nfl_page(), fam="NFL")
    closing(ex, ND + "18:00:00", N_EXP, [], fam="MLB")      # another family


@pytest.fixture
def world(tmp_path):
    db = tmp_path / "copy.db"
    build_db(db)
    ex = tmp_path / "exports"
    write_exports(ex)
    return {"db": db, "ex": ex, "tmp": tmp_path}


def run(w, *extra, ex=None, db=None):
    out = []
    code = rc.main(["--exports", str(ex or w["ex"]), "--db", str(db or w["db"]), *extra], echo=out.append)
    return code, out


def summary(out):
    last = out[-1]
    assert last.startswith(rc.TAG + " ")
    return json.loads(last[len(rc.TAG) + 1:])


def block(out, mid):
    i = next(k for k, ln in enumerate(out) if " · match {} ".format(mid) in ln and ln.startswith("  "))
    return "\n".join(out[i:i + 3])


# ---- the buckets and the HOME gap ------------------------------------------------------------------------------

def test_the_buckets_are_532s_half_open():
    assert rc.bucket(0.0) == "under 1 h"
    assert rc.bucket(0.999) == "under 1 h"
    assert rc.bucket(1.0) == "1-2 h"
    assert rc.bucket(2.0) == "2-3 h"
    assert rc.bucket(3.0) == "3-6 h"
    assert rc.bucket(6.0) == "6-12 h"
    assert rc.bucket(12.0) == "12-24 h"
    assert rc.bucket(23.99) == "12-24 h"
    assert rc.bucket(24.0) == "24 h or more"
    assert rc.bucket(None) == "no stamp"
    assert rc.bucket(-0.01) == "stamp after the export"


def test_soccer_home_gap_by_bucket(world):
    code, out = run(world)
    assert code == 0
    fam = summary(out)["families"]["SOCCER"]
    hg = fam["home_gap"]
    assert hg["under 1 h"]["n"] == 1 and abs(hg["under 1 h"]["median"] - 4.77) < 1e-9
    assert hg["3-6 h"]["n"] == 1
    assert hg["2-3 h"]["n"] == 1
    assert hg["12-24 h"]["n"] == 1
    assert hg["24 h or more"]["n"] == 1
    assert hg["no stamp"]["n"] == 1
    assert hg["stamp after the export"]["n"] == 1
    assert hg["books' session not found"]["n"] == 1     # 539 item 2: a line of its own, never "no stamp"
    assert hg["books' session not found"]["why"] == {"no stored session matches the page": 1}
    assert fam["no_gap"] == {"Kalshi not priced on every leg (not normalised)": 1,
                             "Kalshi's legs mismatched (no price)": 1}
    assert fam["no_stamp_why"] == {"the session's rows unstamped (NULL)": 1}
    assert "HOME gap 4.77 pp" in block(out, 100)
    assert "bucket under 1 h" in block(out, 100)


def test_the_gap_is_absolute_and_computed_not_read(world):
    code, out = run(world)
    b = block(out, 200)
    assert "HOME gap 5.00 pp" in b            # |0.6000 - 0.55|; the page's venue_gap_pp 99.9 is never read
    assert "99.9" not in "\n".join(out)


def test_nfl_by_bucket_and_causes(world):
    code, out = run(world)
    fam = summary(out)["families"]["NFL"]
    hg = fam["home_gap"]
    assert hg["12-24 h"]["n"] == 1 and abs(hg["12-24 h"]["median"] - 5.0) < 1e-9
    assert hg["2-3 h"]["n"] == 2                 # 201, and 206 by capture time (540 item 2(a))
    assert hg["6-12 h"]["n"] == 1
    assert fam["no_gap"] == {"Kalshi not priced on both legs (kalshi_prob null)": 1,
                             "Kalshi's legs mismatched (no price)": 1,
                             "the books' fair is not the 1X2 consensus (fair_source 'spread_derived')": 1}


# ---- the staked rows -------------------------------------------------------------------------------------------

def test_play_in_the_staked_line_ladder_apart(world):
    code, out = run(world)
    st = summary(out)["families"]["SOCCER"]["staked"]
    assert st["PLAY"]["rows"] == 4 and st["LADDER"]["rows"] == 1
    play = st["PLAY"]["by_reference"]
    assert play["under 1 h"]["rows"] == 1
    assert play["no stamp"]["rows"] == 1
    assert play["12-24 h"]["rows"] == 1
    assert play["books' session not found (no stored session matches the page)"]["rows"] == 1
    assert st["PLAY"]["market_ref"] == {"agree": 3, "differ": 1}
    assert st["LADDER"]["by_reference"]["3-6 h"]["rows"] == 1
    assert abs(st["LADDER"]["by_reference"]["3-6 h"]["median"] - 2.15) < 1e-9     # |0.2715 - 0.25|
    assert any(ln.startswith("PLAY (the staked line): rows 4") for ln in out)
    assert any(ln.startswith("LADDER (a line of its own): rows 1") for ln in out)


def test_a_reference_not_the_books_is_counted_apart(world):
    code, out = run(world)
    play = summary(out)["families"]["NFL"]["staked"]["PLAY"]
    assert play["rows"] == 2
    assert play["by_reference"]["reference not the books"]["rows"] == 1
    assert abs(play["by_reference"]["reference not the books"]["median"] - 5.0) < 1e-9   # |0.4 - (1 - 0.55)|
    assert play["by_reference"]["6-12 h"]["rows"] == 1
    assert play["market_ref"] == {"agree": 1, "not checked (reference not the books)": 1}
    assert any("reference not the books (counted apart, no bucket): rows 1" in ln for ln in out)


# ---- the window and the pages ----------------------------------------------------------------------------------

def test_the_first_stamped_row_is_printed_and_earlier_rows_are_out(world):
    code, out = run(world)
    fam = summary(out)["families"]["SOCCER"]
    assert fam["before_first"] == 1                # game 90's page of 11-14, unstamped
    assert fam["first"]["exported_at"] == "2026-11-21 14:27:03Z"
    assert any(ln.startswith("FIRST STAMPED ROW (532 item 4 #7): page closing_SOCCER_2026-11-21T1500Z.json")
               for ln in out)
    assert summary(out)["families"]["NFL"]["before_first"] == 0


def test_no_stamp_column_puts_every_row_out(tmp_path):
    db = tmp_path / "nostamp.db"
    build_db(db, stamp=False)
    ex = tmp_path / "exports"
    write_exports(ex)
    out = []
    code = rc.main(["--exports", str(ex), "--db", str(db)], echo=out.append)
    assert code == 0
    fam = summary(out)["families"]["SOCCER"]
    assert fam["first"] is None and fam["in_window"] == 0
    assert any("ABSENT" in ln for ln in out[:3])


def test_the_latest_page_of_a_start_counts_once(world):
    code, out = run(world)
    sm = summary(out)
    assert sm["pages"]["SOCCER"]["copies"] == 1
    joined = "\n".join(out)
    assert "RE-PAGED START: an earlier page of 2, labelled and out" in joined
    assert "RE-PAGED START: the latest of 2 pages, the one that counts" in joined
    assert "THE LATEST CANNOT BE TOLD" in joined
    assert sm["files"]["undecided_starts:SOCCER"] == 1
    # the earlier page's Kalshi (0.9) never enters: 10 PL rows counted on the counted page, plus 90
    assert sm["families"]["SOCCER"]["rows"] == 11
    assert sm["families"]["SOCCER"]["in_window"] == 10


def test_soccer_reads_pl_2026_27_only_and_other_families_are_counted(world):
    code, out = run(world)
    sm = summary(out)
    assert sm["files"]["other_rows:SOCCER"] >= 2
    assert sm["files"]["other_family"] == 1


def test_bounds(world):
    code, out = run(world, "--from", "2026-11-21T00:00:00Z", "--through", "2026-11-22T00:00:00Z")
    sm = summary(out)
    assert sm["families"]["NFL"]["rows"] == 0
    assert sm["files"]["outside:NFL"] == 1
    assert sm["families"]["SOCCER"]["before_first"] == 0


# ---- what is never read or printed -----------------------------------------------------------------------------

def test_no_amount_unit_order_or_bookmaker_reaches_the_console(world):
    code, out = run(world)
    # the copy's path is printed by design and pytest numbers its folders (pytest-NNNN): it is taken out first
    joined = "\n".join(out).replace(str(world["tmp"]), "<tmp>")
    for s in SENTINELS:
        assert s not in joined, s


class Guard(dict):
    """A desk block that refuses any read of a key the receipt must never touch."""

    def _check(self, k):
        if k not in rc.DESK_READS:
            raise AssertionError("read of desk." + str(k))

    def __getitem__(self, k):
        self._check(k)
        return dict.__getitem__(self, k)

    def get(self, k, default=None):
        self._check(k)
        return dict.get(self, k, default)

    def items(self):
        raise AssertionError("a whole-dict walk of desk")

    def values(self):
        raise AssertionError("a whole-dict walk of desk")

    def __iter__(self):
        raise AssertionError("a whole-dict walk of desk")


def test_only_the_four_desk_keys_are_read():
    r = srow(100, dk=Guard(desk("PLAY", "HOME", "books", 0.4523)))
    got = rc.read_desk(r)
    assert got == {"call": "PLAY", "pick": "HOME", "reference": "books", "market_ref": 0.4523}


# ---- the fence -------------------------------------------------------------------------------------------------

def test_without_a_copy_nothing_is_read(world):
    out = []
    assert rc.main(["--exports", str(world["ex"])], echo=out.append) == 2
    assert out[0].startswith("REFUSED: --db is required")


def test_a_sidecar_is_refused(world):
    Path(str(world["db"]) + "-wal").write_bytes(b"")
    code, out = run(world)
    assert code == 2 and "sidecar" in out[0]


def test_latest_is_refused(world):
    lat = world["ex"] / "latest"
    lat.mkdir()
    code, out = run(world, ex=lat)
    assert code == 2 and "latest/" in out[0]


def test_the_copy_is_unchanged_and_never_written(world):
    before = hashlib.sha256(world["db"].read_bytes()).hexdigest()
    code, _out = run(world)
    assert code == 0
    assert hashlib.sha256(world["db"].read_bytes()).hexdigest() == before
    assert sorted(p.name for p in world["tmp"].iterdir()) == ["copy.db", "exports"]


def test_a_missing_column_is_refused(tmp_path):
    db = tmp_path / "c.db"
    build_db(db)
    import sqlite3
    con = sqlite3.connect(str(db))
    con.execute("ALTER TABLE odds_snapshots DROP COLUMN devig_prob")
    con.commit()
    con.close()
    ex = tmp_path / "exports"
    write_exports(ex)
    out = []
    assert rc.main(["--exports", str(ex), "--db", str(db)], echo=out.append) == 2
    assert out[0] == "REFUSED: columns devig_prob not in odds_snapshots (law 1); nothing read"


def test_no_bytecode_of_the_repo_is_written(world):
    cache = world["tmp"] / "pycache"
    cache.mkdir()
    res = subprocess.run([sys.executable, "-X", "pycache_prefix={}".format(cache), str(SCRIPT), "--exports",
                          str(world["ex"]), "--db", str(world["db"])], capture_output=True, text=True,
                         cwd=str(world["tmp"]), timeout=180)
    assert res.returncode == 0, res.stdout + res.stderr
    own = cache.joinpath(*ROOT.parts[1:])
    assert [p for d in ("src", "scripts") for p in (own / d).rglob("*.pyc")] + list(own.glob("config*.pyc")) == []


def test_it_makes_no_network_call(world, monkeypatch):
    import socket

    def refuse(*a, **k):
        raise AssertionError("a network call")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    code, _out = run(world)
    assert code == 0


# ---- the pre-PR review's findings, pinned ----------------------------------------------------------------------

def test_the_nfl_premise_the_two_de_vigs_differ_at_4_places():
    assert tuple(round(v, 4) for v in PAGE206) != tuple(round(v, 4) for v in POOLED206)


def test_nfl_takes_the_session_by_capture_time_and_counts_the_4_place_agreement(world):
    """540 item 2(a): NFL's session is the latest complete one at or before the export. 206's own fetch (pooled)
    differs from the page at 4 places; the EARLIER session that equals the page is never taken. The agreement is
    counted, and the line_move cross-check agrees with the session taken."""
    code, out = run(world)
    fam = summary(out)["families"]["NFL"]
    assert fam["session_match"] == {rc.VALIDATED: 5, rc.UNVALIDATED: 1}
    b = block(out, 206)
    assert "captured 2026-11-22 17:50:00Z" in b and "by capture time" in b
    assert "bucket 2-3 h" in b and rc.UNVALIDATED in b and "line_move book to_at agree" in b
    assert fam["line_move"] == {"absent": 4, "agree": 1, "differ": 1}
    assert rc.NFL_STAMP in out                    # 540 item 2(d): the NFL lines say what their stamp is


def test_soccer_stays_matched_by_value(world):
    """540 item 2(c): 107's only session differs from the page, so SOCCER finds none (a line of its own)."""
    code, out = run(world)
    b = block(out, 107)
    assert "not found: no stored session matches the page" in b
    assert summary(out)["families"]["SOCCER"]["session_match"] == {rc.VALIDATED: 9, rc.UNVALIDATED: 1}


def _raw_page(folder, name, doc):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(json.dumps(doc))


def test_a_tie_below_the_latest_page_does_not_void_the_start(world, tmp_path):
    ex = tmp_path / "ex2"
    closing(ex / "2026-11-19", SD + "15:00:00", SD + "14:00:00.000000Z", [srow(100)], run_id="run-a")
    closing(ex / "2026-11-20", SD + "15:00:00", SD + "14:00:00.000000Z", [srow(100)], run_id="run-b")
    closing(ex, SD + "15:00:00", S_EXP, [srow(100)], run_id="run-c")
    code, out = run(world, ex=ex)
    sm = summary(out)
    assert sm["pages"]["SOCCER"]["counted"] == 1
    assert sm["families"]["SOCCER"]["rows"] == 1


def test_a_copy_of_a_page_with_no_run_start_is_never_counted_twice(world, tmp_path):
    ex = tmp_path / "ex3"
    doc = {"exported_at": S_EXP, "git_sha": "x", "predictions": [srow(100)],
           "closing": {"family": "SOCCER", "run_id": "run-x"}}
    _raw_page(ex, "closing_SOCCER_2026-13-40T2500Z.json", doc)
    _raw_page(ex / "2026-11-22", "closing_SOCCER_2026-13-40T2500Z.json", doc)
    code, out = run(world, ex=ex)
    sm = summary(out)
    assert sm["pages"]["SOCCER"] == {"read": 2, "counted": 1, "copies": 1}
    assert sm["families"]["SOCCER"]["rows"] == 1


def test_a_page_with_no_exported_at_is_placed_by_its_run_start(world, tmp_path):
    ex = tmp_path / "ex4"
    closing(ex, SD + "15:00:00", S_EXP, [srow(100)])
    closing(ex, "2026-11-14T15:00:00", None, [srow(90)])          # before the first stamped row: out
    closing(ex, "2026-11-28T15:00:00", None, [srow(101)])         # after it: in, its cause counted
    code, out = run(world, ex=ex)
    fam = summary(out)["families"]["SOCCER"]
    assert fam["before_first"] == 1 and fam["in_window"] == 2 and fam["unplaced"] == 0
    assert fam["home_gap"]["books' session not found"]["why"] == {"the page has no readable exported_at": 1}


def test_a_family_with_no_stamped_row_counts_its_rows_once(tmp_path):
    db = tmp_path / "nostamp.db"
    build_db(db, stamp=False)
    ex = tmp_path / "exports"
    write_exports(ex)
    out = []
    rc.main(["--exports", str(ex), "--db", str(db)], echo=out.append)
    fam = summary(out)["families"]["NFL"]
    assert fam["before_first"] == 0 and fam["out_no_stamped_row"] == fam["rows"] == 7


# ---- #1140 (543 item 2(d)): the causes of the two unknowns over every row in the window -----------------------

def test_the_not_found_causes_count_the_rows_with_no_gap_too(world):
    """NFL game 203 (a spread-derived fair: no gap, no session) was counted in the every-row line but in no cause."""
    code, out = run(world)
    nfl = summary(out)["families"]["NFL"]
    assert nfl["home_gap"]["books' session not found"]["n"] == 0          # the gap distribution: rows with a gap
    assert nfl["not_found_why_all"] == {
        "the books' fair is not the 1X2 consensus (fair_source 'spread_derived')": 1}
    soccer = summary(out)["families"]["SOCCER"]
    assert soccer["not_found_why_all"] == {"no stored session matches the page": 1}
    # the printed line, not only the JSON: the console is what the run's reader sees
    assert any(ln == "    books' session not found, every row in the window (gap or none), by cause: the books' fair "
               "is not the 1X2 consensus (fair_source 'spread_derived') 1" for ln in out)


def test_the_no_stamp_causes_count_the_rows_with_no_gap_too(world, tmp_path):
    ex = tmp_path / "ex1140"
    closing(ex, SD + "15:00:00", S_EXP, [srow(100), srow(103, normalized=False)])   # 103: unstamped, no gap
    code, out = run(world, ex=ex)
    fam = summary(out)["families"]["SOCCER"]
    assert fam["home_gap"]["no stamp"]["n"] == 0
    assert fam["no_stamp_why"] == {}
    assert fam["no_stamp_why_all"] == {"the session's rows unstamped (NULL)": 1}
    assert any(ln == "    no stamp, every row in the window (gap or none), by cause: the session's rows unstamped "
               "(NULL) 1" for ln in out)


def test_every_cause_breakdown_sums_to_its_every_row_count(world):
    code, out = run(world)
    for name, fam in summary(out)["families"].items():
        allb = fam["by_bucket_all"]
        assert sum(fam["not_found_why_all"].values()) == allb.get("books' session not found", 0), name
        assert sum(fam["no_stamp_why_all"].values()) == allb.get("no stamp", 0), name
