"""THE QB HOLD, MEASURED (#446; addendum 44 item 9; the build, addendum 209 item 3; the would-be rows, addendum 217 item
4; its two questions ruled, addendum 223 item 5): scripts/qb_hold_receipt.py, read-only.

The world is synthetic: NFL Desk rows made by desk_policy.annotate (the real shape: the PLAY rows of 2026-10-11 with
addendum 214's rule off, as main ran them then; a would-be row with it on), written into closing files as a closing run
writes them (tests/test_void_redated.py write_closing), a throwaway SQLite world copied by the .backup API (the copy the
script reads), and a synthetic Cockpit ledger export. Pins: #446's two first rows reproduced in shape (Cleveland @ NY
Jets, Baltimore @ Atlanta, 2026-10-11: what the page said, the price it named, the close, the result, "not established");
what was done printed as the ledger holds it, under its own label ("fills", each entry's ticker, side, title, opened,
closed as held), never relabelled, the same rule on a would-be row (223 item 5(a)), and never a quantity, price, fee,
P&L, unit or dollar figure of the ledger; the would-be rows on their own lines, labelled, counted toward thirty, no
price but the page's (none); the two sources in the header and a game the copy lacks labelled "no result in this copy",
never scored (223 item 5(b)); each unscored row (no result in this copy, teams differ, re-dated void) counted toward
thirty, labelled, outside the W-L-P (225 item 3); one machine's pair (231 item 2(a), (b)): host/ read, the mirror's
dated folders read and latest/ never, the SOURCES line naming the directory and the copy read; what was done on every
row, scored or unscored, and the LEDGER line's counts over every row of a kind (231 item 2(c)); one run's count under
its era's bound (232 item 2): --from inclusive, --through exclusive on the closing run's start, UTC, KC@SEA the laptop's
row and the host's rehearsal of it excluded by the bound and named, a run start at the bound the host era's, a row with
no run start outside every bound, the labels as ruled, this_run_thirty_reached; the refusals.
"""
import importlib.util
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.walters import desk_policy as dp
from src.walters.venue import kalshi_exec
from tests.test_void_redated import write_closing

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("qb_hold_receipt", ROOT / "scripts" / "qb_hold_receipt.py")
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)

KO_1011 = datetime(2026, 10, 11, 17, 0)        # 13:00 ET
KO_1018 = datetime(2026, 10, 18, 20, 5)        # 16:05 ET
KO_1109 = datetime(2026, 11, 9, 18, 0)         # 13:00 ET, after addendum 214
WOULD = "would-be PLAY (uncertified, unstaked)"
UNBOUNDED = "unbounded run (no --from, no --through: no era; not an era's count)"
COUNT_HEAD = ("COUNT toward thirty, THIS RUN'S (#446; addendum 44 item 9, 209 item 3; would-be rows counted too, labelled, "
              "217 item 4; unscored rows counted too, labelled, outside the W-L-P, 225 item 3; one run's count, 232 item "
              "2(a)): ")
BELOW = ("this run's count; #446's count toward thirty is the architect's sum of the two runs' consoles, on #446 (232 "
         "item 2(a)); not read before thirty rows or the season's end (no verdict is computed here)")
# figures a synthetic fill carries: none of them may ever reach the output
FILL_FIGURES = ("137", "0.4321", "57.89", "1.23", "59.12")


def nfl_row(mid, away, home, ca, ch, p_home, fair_h, bid_h, ask_h, ko, *, qb_side=None, qb=(), empty_side=None):
    inj = {s: {"count": 0 if s == empty_side else 2, "qb_listed": list(qb) if s == qb_side else []}
           for s in ("home", "away")}
    ev = f"KXNFLGAME-{ko:%y}{ko:%b}".upper() + f"{ko:%d}{ca}{ch}"
    r = {"match_id": mid, "home_team": home, "away_team": away, "utc_date": ko.strftime("%Y-%m-%dT%H:%M:%S"),
         "competition": "NFL", "stage": "regular",
         "kalshi_legs": {"HOME": {"ticker": f"{ev}-{ch}", "bid": bid_h, "ask": ask_h},
                         "AWAY": {"ticker": f"{ev}-{ca}", "bid": round(1 - ask_h, 2), "ask": round(1 - bid_h, 2)}},
         "prediction": {"probabilities": {"home_win": p_home, "draw": None, "away_win": round(1 - p_home, 4)},
                        "tier": "lean"},
         "market": {"bookmaker_count": 9, "fair_prob": {"HOME": fair_h, "AWAY": round(1 - fair_h, 4)}},
         "input_quality": {"injuries": inj}}
    r.update(kalshi_exec(bid_h, ask_h, "NFL", two_way=True))
    return r


def annotated(rows, ko, *, market_only):
    doc = {"sport": "nfl", "predictions": [json.loads(json.dumps(r)) for r in rows]}
    now = (ko - timedelta(minutes=35)).replace(tzinfo=timezone.utc)
    if market_only:
        dp.annotate(doc, now=now)
    else:
        with dp.nfl_market_only_rule_off():
            dp.annotate(doc, now=now)
    return doc["predictions"]


def cle_nyj():
    return nfl_row(101, "Cleveland Browns", "New York Jets", "CLE", "NYJ", 0.45, 0.58, 0.56, 0.57, KO_1011,
                   qb_side="away", qb=["Dillon Gabriel"])


def bal_atl():
    return nfl_row(102, "Baltimore Ravens", "Atlanta Falcons", "BAL", "ATL", 0.48, 0.60, 0.62, 0.63, KO_1011,
                   qb_side="away", qb=["Lamar Jackson"])


def clean():                                       # a QB-clean PLAY: never a row of this receipt
    return nfl_row(103, "Detroit Lions", "Chicago Bears", "DET", "CHI", 0.45, 0.58, 0.56, 0.57, KO_1011)


def kc_lv():                                       # the empty-list rule: "QB unread half units"
    return nfl_row(104, "Kansas City Chiefs", "Las Vegas Raiders", "KC", "LV", 0.55, 0.43, 0.42, 0.43, KO_1018,
                   empty_side="home")


def lost_row():                                    # a QB-flagged PLAY whose match id this database lacks
    return nfl_row(999, "Miami Dolphins", "Buffalo Bills", "MIA", "BUF", 0.45, 0.58, 0.56, 0.57, KO_1018,
                   qb_side="away", qb=["Tua Tagovailoa"])


def sea_lar():                                     # after addendum 214: the would-be PLAY
    return nfl_row(105, "Seattle Seahawks", "Los Angeles Rams", "SEA", "LAR", 0.45, 0.58, 0.56, 0.57, KO_1109,
                   qb_side="away", qb=["Sam Darnold"])


def lost_would():                                  # a would-be row whose match id this database lacks
    return nfl_row(998, "New York Giants", "Philadelphia Eagles", "NYG", "PHI", 0.45, 0.58, 0.56, 0.57, KO_1109,
                   qb_side="away", qb=["Jaxson Dart"])


def _world(path: Path, moved: dict | None = None, extra: tuple = ()):
    from src.db.schema import Base, Competition, Match, MatchStatus, Odds, Sport, Team
    eng = create_engine(f"sqlite:///{path}", future=True)
    Base.metadata.create_all(eng)
    games = ((101, "Cleveland Browns", "New York Jets", KO_1011, 17, 12, MatchStatus.FINISHED, (1.65, 2.3)),
             (102, "Baltimore Ravens", "Atlanta Falcons", KO_1011, 23, 30, MatchStatus.FINISHED, (1.55, 2.5)),
             (103, "Detroit Lions", "Chicago Bears", KO_1011, 20, 24, MatchStatus.FINISHED, (1.65, 2.3)),
             (104, "Kansas City Chiefs", "Las Vegas Raiders", KO_1018, 21, 17, MatchStatus.FINISHED, (2.2, 1.7)),
             (105, "Seattle Seahawks", "Los Angeles Rams", KO_1109, None, None, MatchStatus.SCHEDULED, None),
             *((mid, away, home, ko, hs, as_, MatchStatus.FINISHED, None) for mid, away, home, ko, hs, as_ in extra))
    with Session(eng) as s:
        c = Competition(sport=Sport.NFL, code="NFL", name="NFL", area="X", type="LEAGUE")
        s.add(c)
        s.flush()
        for mid, away, home, ko, hs, as_, st, px in games:
            h, a = Team(sport=Sport.NFL, name=home), Team(sport=Sport.NFL, name=away)
            s.add_all([h, a])
            s.flush()
            s.add(Match(id=mid, sport=Sport.NFL, competition_id=c.id, season="2026",
                        utc_date=(moved or {}).get(mid, ko), status=st,
                        home_team_id=h.id, away_team_id=a.id, home_score=hs, away_score=as_))
            if px:
                for bk in ("bk1", "bk2"):
                    for sel, p in zip(("HOME", "AWAY"), px):
                        s.add(Odds(match_id=mid, bookmaker=bk, market="1X2", selection=sel, price_decimal=p,
                                   captured_at=ko - timedelta(hours=1)))
        s.commit()
    eng.dispose()


def _backup(src: Path, dst: Path) -> Path:
    """A .backup-API copy (sqlite3's online backup), as the operator's block takes it."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    a, b = sqlite3.connect(str(src)), sqlite3.connect(str(dst))
    a.backup(b)
    b.close()
    a.close()
    return dst


def _fill(fid, ticker, side, title, closed=True):
    return {"id": fid, "ticker": ticker, "side": side, "qty": 137, "entry": 0.4321, "exit": 1.0 if closed else None,
            "staked": 59.12, "fees": 1.23, "open_fee": 1.23, "close_fee": 0, "pnl_pre": 59.12, "pnl_net": 57.89,
            "opened": "2026-10-18T19:31:00Z", "closed": "2026-10-19T00:10:00Z" if closed else None, "title": title}


LEDGER = {"calls": [{"id": "c1", "sport": "NFL", "home": "Las Vegas Raiders", "away": "Kansas City Chiefs",
                     "pick": "HOME", "match_id": 104, "units": 0.5, "status": "graded"}],
          "fills": [_fill("f-lv", "KXNFLGAME-26OCT18KCLV-LV", "yes", "Las Vegas wins — Kansas City"),
                    _fill("f-sea", "KXNFLGAME-26NOV09SEALAR-SEA", "no", "Seattle wins — Los Angeles R", closed=False),
                    _fill("f-mlb", "KXMLBGAME-26OCT18NYYBOS-BOS", "yes", "Boston wins — New York Y")],
          "meta": {"auto_claims": []}}


@pytest.fixture
def world(tmp_path):
    ex = tmp_path / "exports"
    write_closing(ex, KO_1011 - timedelta(minutes=35),
                  annotated([cle_nyj(), bal_atl(), clean()], KO_1011, market_only=False), fam="NFL")
    write_closing(ex, KO_1018 - timedelta(minutes=35),
                  annotated([kc_lv(), lost_row()], KO_1018, market_only=False), fam="NFL")
    write_closing(ex, KO_1109 - timedelta(minutes=35), annotated([sea_lar(), lost_would()], KO_1109, market_only=True),
                  fam="NFL")
    _world(tmp_path / "world.db")
    copy = _backup(tmp_path / "world.db", tmp_path / "copy" / "nfl.db")
    led = tmp_path / "bd_ledger_v1_2026-11-02.json"
    led.write_text(json.dumps(LEDGER))
    return {"ex": ex, "copy": copy, "ledger": led}


def _run(capsys, *args):
    rc = script.main([str(a) for a in args])
    return rc, capsys.readouterr().out.splitlines()


def _line(out, game):
    hit = [ln for ln in out if f" · {game} [match " in ln]
    assert len(hit) == 1, (game, out)
    return hit[0]


# ---- the rows ------------------------------------------------------------------------------------------------------

def test_the_desk_rows_are_the_real_shape():
    """The fixture's rows are the Desk's own: a QB-flagged PLAY at the ask on 10-11, and the would-be row of 214."""
    d = {r["match_id"]: r["desk"] for r in annotated([cle_nyj(), bal_atl(), clean()], KO_1011, market_only=False)}
    assert d[101]["call"] == d[102]["call"] == d[103]["call"] == "PLAY"
    assert "QB-flagged half units" in d[101]["tags"] and "QB-flagged half units" not in d[103]["tags"]
    assert (d[101]["pick"], d[101]["order"]["limit"]) == ("AWAY", 0.44)
    assert (d[102]["pick"], d[102]["order"]["limit"]) == ("AWAY", 0.38)
    w = annotated([sea_lar()], KO_1109, market_only=True)[0]["desk"]
    assert (w["call"], w["pass_kind"], w["market_only_hold"]["would_call"]) == ("PASS", "market_only", "PLAY")
    assert script.classify(w) == "would" and script.classify(d[101]) == "play" and script.classify(d[103]) is None


def test_446s_first_two_rows_reproduced_in_shape(world, capsys):
    rc, out = _run(capsys, "--db", world["copy"], "--exports", world["ex"], "--ledger", world["ledger"])
    assert rc == 0, out
    cle = _line(out, "Cleveland Browns @ New York Jets")
    assert cle.startswith("- 2026-10-11 13:00 ET · Cleveland Browns @ New York Jets [match 101] · page: PLAY AWAY "
                          "(Cleveland Browns) · QB: QB-flagged half units — QB-flagged (Dillon Gabriel) → half units · "
                          "exec edge +"), cle
    assert " · price named: limit 0.44 (take at the ask (spread 1c)) · close 0." in cle
    assert " (books) · result: lost 12-17 (away-home) · what was done: not established" in cle
    bal = _line(out, "Baltimore Ravens @ Atlanta Falcons")
    assert "page: PLAY AWAY (Baltimore Ravens) · QB: QB-flagged half units — QB-flagged (Lamar Jackson) → half units" \
        in bal
    assert " · price named: limit 0.38 (take at the ask (spread 1c)) · " in bal
    assert bal.endswith(" · result: won 30-23 (away-home) · what was done: not established"), bal
    assert not [ln for ln in out if "Detroit Lions" in ln]                      # QB-clean: never a row here


def test_what_was_done_is_what_the_ledger_holds_under_its_own_label(world, capsys):
    """223 item 5(a): "what was done" prints what the LEDGER holds, under the ledger's own label for it (the export's
    "fills", each entry's own field names and values as held); the script reports and never relabels (no "position",
    no "operator's own fill", no side resolved to the page's); the same rule on a would-be row; a row with no entry
    is blank ("not established", 46 item 4)."""
    rc, out = _run(capsys, "--db", world["copy"], "--exports", world["ex"], "--ledger", world["ledger"])
    assert rc == 0
    kc = _line(out, "Kansas City Chiefs @ Las Vegas Raiders")
    assert ("QB: QB unread half units — injury list empty (Las Vegas Raiders): QB rule unread → half units"
            in kc), kc
    assert kc.endswith('result: won 17-21 (away-home) · what was done: fills: {"ticker": "KXNFLGAME-26OCT18KCLV-LV", '
                       '"side": "yes", "title": "Las Vegas wins — Kansas City", "opened": "2026-10-18T19:31:00Z", '
                       '"closed": "2026-10-19T00:10:00Z"}'), kc
    i_play = out.index("PLAY (the Desk's call), QB-flagged or unread — 3 scored rows, by kickoff")
    i_would = out.index(f"{WOULD} — 1 scored row, by kickoff")
    sea = _line(out, "Seattle Seahawks @ Los Angeles Rams")
    assert out.index(sea) == i_would + 1 and i_play < i_would
    assert (f"page: PASS (market-only, addendum 214); {WOULD}: AWAY (Seattle Seahawks) · QB: QB-flagged half units — "
            "QB-flagged (Sam Darnold) → half units") in sea
    assert " · price named: none (PASS on the page) · close " in sea                  # no other price (223 item 5)
    assert sea.endswith('result: open (not final) · what was done: fills: {"ticker": "KXNFLGAME-26NOV09SEALAR-SEA", '
                        '"side": "no", "title": "Seattle wins — Los Angeles R", "opened": "2026-10-18T19:31:00Z", '
                        '"closed": null}'), sea
    for ln in out:                                                     # never relabelled (223 item 5(a))
        if not ln.startswith(("- ", "LEDGER:")):
            continue
        for word in ("position", "operator's own", "the page's side", "the other side", "holds "):
            assert word not in ln, (word, ln)
    assert ("LEDGER: NFL game fills entries read 2 · fitting more than one row (ambiguous, given to none) 0 · PLAY rows "
            f"(scored + unscored) with fills on the game 1 of 4 · {WOULD} rows (scored + unscored) with fills on the "
            "game 1 of 2") in out
    assert not [ln for ln in out if ln.startswith("LEDGER:") and "not matched to" in ln]   # 231 item 2(c): dropped
    count = [ln for ln in out if ln.startswith("COUNT toward thirty")]
    assert count == [f"{COUNT_HEAD}{UNBOUNDED}: 6 of 30 (PLAY 4 + {WOULD} 2) — {BELOW} · "
                     "PLAY W-L-P 2-1-0, void 0, open 0, unscored 1 (no result in this copy 1 · teams differ 0 · "
                     f"re-dated void 0) · {WOULD} W-L-P 0-0-0, void 0, open 1, unscored 1 (no result in this copy 1 · "
                     "teams differ 0 · re-dated void 0)"]
    assert out[-1].startswith("QB-HOLD-RECEIPT ")
    j = json.loads(out[-1][len("QB-HOLD-RECEIPT "):])
    assert (j["play_rows"], j["would_be_rows"], j["toward_thirty"], j["this_run_thirty_reached"]) == (3, 1, 6, False)
    assert j["counted"] == {"play": 4, "would_be": 2}
    assert j["what_was_done"] == {"play": {"fills": 1, "not_established": 3},          # every row: 3 scored + 1
                                  "would_be": {"fills": 1, "not_established": 1}}      # 1 scored + 1 unscored


def test_a_would_be_row_with_no_ledger_entry_stays_blank(world, capsys, tmp_path):
    """223 item 5(a): "a would-be row with no ledger position stays blank" — the blank a PLAY row has (46 item 4)."""
    led = tmp_path / "led-blank.json"
    led.write_text(json.dumps({**LEDGER, "fills": [f for f in LEDGER["fills"] if f["id"] != "f-sea"]}))
    rc, out = _run(capsys, "--db", world["copy"], "--exports", world["ex"], "--ledger", led)
    assert rc == 0
    assert _line(out, "Seattle Seahawks @ Los Angeles Rams").endswith("what was done: not established")
    assert _line(out, "Cleveland Browns @ New York Jets").endswith("what was done: not established")
    j = json.loads(out[-1][len("QB-HOLD-RECEIPT "):])
    assert j["what_was_done"]["would_be"] == {"fills": 0, "not_established": 2}


def test_the_two_sources_and_no_result_in_this_copy(world, capsys):
    """223 item 5(b): the results from the DB copy stay; the header names the copy and the closing-file directory as
    the two sources; a row whose game the copy lacks is labelled "no result in this copy", never scored, and (225 item
    3) counted toward thirty as a labelled, unscored row."""
    rc, out = _run(capsys, "--db", world["copy"], "--exports", world["ex"], "--ledger", world["ledger"])
    assert rc == 0
    src = [ln for ln in out if ln.startswith("SOURCES")]
    assert len(src) == 1 and src[0].startswith(f"SOURCES (the two, 223 item 5(b); one machine's pair, 231 item 2(a)): "
                                               f"the copy read {Path(world['copy']).resolve()} (--db; a .backup copy, "
                                               "opened mode=ro&immutable=1; the results, as results-tally reads them: "
                                               "exec_cohorts.result_of) · the closing-file directory read "
                                               f"{Path(world['ex']).resolve()} (--exports {world['ex']}; closing_*.json "
                                               "there and in its dated folders <YYYY-MM-DD>/ 0, never latest/"), src
    assert f"WHAT WAS DONE FROM: ledger {world['ledger']} (bd_ledger_v1: calls 1, fills 3)" in out
    assert (f"UNSCORED (counted toward thirty, labelled, never scored, outside the W-L-P, 225 item 3; per kind, never "
            f"pooled): PLAY — no result in this copy 1 · teams differ 0 · re-dated void 0 (re-dated 0 · placeholder "
            f"kickoff 0); {WOULD} — no result in this copy 1 · teams differ 0 · re-dated void 0 (re-dated 0 · "
            "placeholder kickoff 0)") in out
    assert ("  no result in this copy (unscored, counted): match 999 Miami Dolphins @ Buffalo Bills (PLAY) · what was "
            "done: not established") in out
    assert (f"  no result in this copy (unscored, counted): match 998 New York Giants @ Philadelphia Eagles ({WOULD}) · "
            "what was done: not established" in out)
    assert not [ln for ln in out if ln.startswith("- ") and ("[match 999]" in ln or "[match 998]" in ln)]
    assert not [ln for ln in out if "not in this database" in ln]
    j = json.loads(out[-1][len("QB-HOLD-RECEIPT "):])
    assert j["unscored"] == {"play": {"no_result": 1, "teams": 0, "void": 0},
                             "would_be": {"no_result": 1, "teams": 0, "void": 0}}
    assert (j["counted"], j["toward_thirty"]) == ({"play": 4, "would_be": 2}, 6)
    assert (j["play_record"], j["would_be_record"]) == ({"win": 2, "loss": 1, "push": 0, "void": 0, "open": 0},
                                                        {"win": 0, "loss": 0, "push": 0, "void": 0, "open": 1})


def _numbers(j, path=()):
    for k, v in j.items():
        if isinstance(v, dict):
            yield from _numbers(v, path + (k,))
        elif isinstance(v, int) and not isinstance(v, bool):
            yield path + (k,), v


def test_play_and_would_be_are_never_pooled_but_in_the_count_toward_thirty(world, capsys):
    """217 item 4: the would-be rows are "never pooled with PLAY"; "#446's read at thirty rows counts those rows too,
    labelled". The count toward thirty is the one figure that adds the two kinds: every other row count, printed or in
    the JSON, is per kind. The world has PLAY 3 scored (one with fills) + 1 unscored, and would-be 1 scored (with
    fills) + 1 unscored (225 item 3: counted): a pooled figure would read 6 counted (the LEDGER line's "of", every row
    of a kind since 231 item 2(c)), 2 with fills, 2 with no result in this copy."""
    rc, out = _run(capsys, "--db", world["copy"], "--exports", world["ex"], "--ledger", world["ledger"])
    assert rc == 0
    count = [ln for ln in out if ln.startswith("COUNT toward thirty")]
    assert len(count) == 1 and f"{UNBOUNDED}: 6 of 30 (PLAY 4 + {WOULD} 2)" in count[0]
    for ln in out:
        if ln in count or ln.startswith(("RULING", "KEYS", "SOURCES", "WHAT WAS DONE FROM", "QB-HOLD-RECEIPT")):
            continue
        assert not re.search(r"\bof 6\b", ln), ln                       # rows, both kinds: only the count's
        assert not re.search(r"(fills on the game|no result in this copy) 2\b", ln), ln
        assert not re.search(r"\b2 of\b", ln), ln
    j = json.loads(out[-1][len("QB-HOLD-RECEIPT "):])
    # every row count lives under a kind's key; the whitelisted top-level figures are not row tallies of both kinds
    whole = {("closing_files",), ("unreadable",), ("nfl_games",), ("read_at",), ("ambiguous_fills",),
             ("toward_thirty",), ("play_rows",), ("would_be_rows",), ("dated_folders",)}
    for path, v in _numbers(j):
        if path in whole:
            continue
        assert path[0] in ("play_record", "would_be_record") or "play" in path or "would_be" in path, path
    assert j["toward_thirty"] == j["counted"]["play"] + j["counted"]["would_be"]
    for k, rows in (("play", "play_rows"), ("would_be", "would_be_rows")):     # each kind: scored + unscored
        assert j["counted"][k] == j[rows] + sum(j["unscored"][k].values())
    pooled = [path for path, v in _numbers(j)
              if path not in {("toward_thirty",), ("nfl_games",), ("closing_files",), ("read_at",)} and v == 6]
    assert not pooled, pooled


def test_no_quantity_price_fee_or_pnl_of_the_ledger_and_no_unit_is_ever_printed(world, capsys):
    """209 item 3 ("no figure of the unit, no fill size") and 223 item 5(a) ("It prints NO quantity, price, fee or P&L
    for any row"): the fills carry distinctive figures (quantity, entry, exit, fee, stake, P&L) and an id that is the
    CSV row; the PLAY rows an order of contracts with a unit label; the would-be row a record exec cost (the ask plus
    the taker fee). None reaches the output, and no ledger field but ticker, side, title, opened and closed is ever
    printed. The page's named price and the close stay (44 item 9)."""
    rc, out = _run(capsys, "--db", world["copy"], "--exports", world["ex"], "--ledger", world["ledger"])
    assert rc == 0
    text = "\n".join(out)
    assert "$" not in text
    assert not re.search(r"\b\d+(\.\d+)?\s?u\b", text), re.search(r"\b\d+(\.\d+)?\s?u\b", text)
    for word in ("contracts", "× ", "qty", "pnl", "SP_UNIT_USD", "BUY YES", "BUY NO", "exec cost"):
        assert word not in text, word
    body = "\n".join(ln for ln in out if not ln.startswith(("RULING", "SOURCES", "WHAT WAS DONE FROM")))  # tmp paths
    for fig in FILL_FIGURES:
        assert fig not in body, fig
    for key in ("qty", "entry", "exit", "staked", "fees", "open_fee", "close_fee", "pnl_pre", "pnl_net", "id",
                "units", "price"):
        assert f'"{key}"' not in body, key
    held = [json.loads(m) for ln in out if ln.startswith("- ") for m in re.findall(r"\{[^{}]*\}", ln)]
    assert len(held) == 2 and all(list(h) == ["ticker", "side", "title", "opened", "closed"] for h in held), held
    sea = _line(out, "Seattle Seahawks @ Los Angeles Rams")
    cost = annotated([sea_lar()], KO_1109, market_only=True)[0]["desk"]["exec"]["cost"]
    assert f"{cost:.3f}" not in sea and "price named: none (PASS on the page) · " in sea, (cost, sea)
    assert "price named: limit 0.44 (" in _line(out, "Cleveland Browns @ New York Jets")      # the page's price stays
    j = json.loads(out[-1][len("QB-HOLD-RECEIPT "):])
    assert not {"units", "unit", "qty", "stake", "staked", "pnl", "fees", "contracts", "price"} & set(j)


def test_without_a_ledger_what_was_done_reads_not_read(world, capsys):
    rc, out = _run(capsys, "--db", world["copy"], "--exports", world["ex"])
    assert rc == 0
    assert _line(out, "Kansas City Chiefs @ Las Vegas Raiders").endswith("what was done: not read (no --ledger)")
    assert not [ln for ln in out if ln.startswith("LEDGER:") or (ln.startswith("- ") and "not established" in ln)]
    assert "WHAT WAS DONE FROM: ledger not read (no --ledger): 'what was done' reads not read" in out
    j = json.loads(out[-1][len("QB-HOLD-RECEIPT "):])
    assert j["ledger_read"] is False and j["what_was_done"] is None
    sea = _line(out, "Seattle Seahawks @ Los Angeles Rams")
    assert sea.endswith("what was done: not read (no --ledger)"), sea


def test_an_ambiguous_fill_is_given_to_no_row(world, capsys, tmp_path):
    """A fill with no event the rows name, fitting two rows by the game matcher, is counted ambiguous, given to none
    (refusals stay refusals)."""
    rows = annotated([cle_nyj()], KO_1011, market_only=False)
    twin = json.loads(json.dumps(rows[0]))
    twin["match_id"] = 106
    write_closing(tmp_path / "ex2", KO_1011 - timedelta(minutes=35), rows + [twin], fam="NFL")
    _world(tmp_path / "w2.db")
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team
    eng = create_engine(f"sqlite:///{tmp_path / 'w2.db'}", future=True)
    with Session(eng) as s:
        c = s.query(Competition).one()
        h, a = Team(sport=Sport.NFL, name="New York Jets"), Team(sport=Sport.NFL, name="Cleveland Browns")
        s.add_all([h, a])
        s.flush()
        s.add(Match(id=106, sport=Sport.NFL, competition_id=c.id, season="2026", utc_date=KO_1011,
                    status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id, home_score=17, away_score=12))
        s.commit()
    eng.dispose()
    copy = _backup(tmp_path / "w2.db", tmp_path / "c2" / "nfl.db")
    led = tmp_path / "led2.json"
    led.write_text(json.dumps({"calls": [], "fills": [_fill("f", "KXNFLGAME-26OCT11CLENYJX-CLE", "yes",
                                                            "Cleveland wins — New York J")]}))
    rc, out = _run(capsys, "--db", copy, "--exports", tmp_path / "ex2", "--ledger", led)
    assert rc == 0, out
    assert ("LEDGER: NFL game fills entries read 1 · fitting more than one row (ambiguous, given to none) 1 · PLAY rows "
            f"(scored + unscored) with fills on the game 0 of 2 · {WOULD} rows (scored + unscored) with fills on the game "
            "0 of 0") in out


def test_a_re_dated_row_is_void_named_unscored_and_counted(world, capsys, tmp_path):
    """exec_cohorts' rule: a game none of whose closing rows is within the hour of its current start is void with
    redated's label, named under UNSCORED, never scored, and (225 item 3) counted toward thirty, labelled."""
    _world(tmp_path / "w3.db", moved={102: KO_1011 + timedelta(days=1)})
    copy = _backup(tmp_path / "w3.db", tmp_path / "c3" / "nfl.db")
    rc, out = _run(capsys, "--db", copy, "--exports", world["ex"])
    assert rc == 0, out
    assert not [ln for ln in out if ln.startswith("- ") and "Baltimore Ravens" in ln]
    assert (f"UNSCORED (counted toward thirty, labelled, never scored, outside the W-L-P, 225 item 3; per kind, never "
            f"pooled): PLAY — no result in this copy 1 · teams differ 0 · re-dated void 1 (re-dated 1 · placeholder "
            f"kickoff 0); {WOULD} — no result in this copy 1 · teams differ 0 · re-dated void 0 (re-dated 0 · "
            "placeholder kickoff 0)") in out
    assert ("  re-dated void (unscored, counted): match 102 Baltimore Ravens @ Atlanta Falcons (PLAY): void: re-dated "
            "2026-10-11 17:00Z → 2026-10-12 17:00Z · what was done: not read (no --ledger)") in out
    j = json.loads(out[-1][len("QB-HOLD-RECEIPT "):])
    assert (j["toward_thirty"], j["counted"], j["play_rows"]) == (6, {"play": 4, "would_be": 2}, 2)
    assert j["play_record"] == {"win": 1, "loss": 1, "push": 0, "void": 0, "open": 0}       # 102 not in the W-L-P


def test_a_placeholder_kickoff_void_is_split_beside_the_void_head(world, capsys, tmp_path):
    """One void state, two labels (addendum 109 item 2 Q2): a row recorded at the 04:00Z placeholder whose match is now
    at 17:00Z reads redated's "void: placeholder kickoff". It counts toward thirty under 225 item 2(a)'s cause head,
    unscored, and the UNSCORED line splits the head as redated.void_counts does: "re-dated 0 · placeholder kickoff 1"."""
    ph = nfl_row(102, "Baltimore Ravens", "Atlanta Falcons", "BAL", "ATL", 0.48, 0.60, 0.62, 0.63,
                 KO_1011.replace(hour=4), qb_side="away", qb=["Lamar Jackson"])
    ex = tmp_path / "ex6"
    write_closing(ex, KO_1011 - timedelta(minutes=35), annotated([cle_nyj()], KO_1011, market_only=False)
                  + annotated([ph], KO_1011.replace(hour=4), market_only=False), fam="NFL")
    rc, out = _run(capsys, "--db", world["copy"], "--exports", ex)
    assert rc == 0, out
    assert ("  re-dated void (unscored, counted): match 102 Baltimore Ravens @ Atlanta Falcons (PLAY): void: "
            "placeholder kickoff · what was done: not read (no --ledger)") in out
    assert (f"UNSCORED (counted toward thirty, labelled, never scored, outside the W-L-P, 225 item 3; per kind, never "
            f"pooled): PLAY — no result in this copy 0 · teams differ 0 · re-dated void 1 (re-dated 0 · placeholder "
            f"kickoff 1); {WOULD} — no result in this copy 0 · teams differ 0 · re-dated void 0 (re-dated 0 · "
            "placeholder kickoff 0)") in out
    assert not [ln for ln in out if ln.startswith("- ") and "Baltimore Ravens" in ln]
    j = json.loads(out[-1][len("QB-HOLD-RECEIPT "):])
    assert (j["counted"], j["play_rows"], j["unscored"]["play"]) == ({"play": 2, "would_be": 0}, 1,
                                                                      {"no_result": 0, "teams": 0, "void": 1})


# ---- 225 item 3 (Q1, by 225 item 2(a)): the unscored rows count toward thirty, labelled, outside the W-L-P -----------

def test_each_unscored_kind_counts_toward_thirty_with_its_label_and_never_in_the_w_l_p(capsys, tmp_path):
    """225 item 3: "a row the copy lacks ("no result in this copy"), a teams-differ row and a void row each COUNT toward
    thirty as labelled, unscored rows, kept outside the W-L-P with their label". The world: PLAY 101 scored (lost),
    999 the copy lacks, 103 whose teams are not the copy's match 103, 102 re-dated; would-be 105 scored (open), 998 the
    copy lacks, 104 whose teams differ. Each of the three causes is counted, named with its label, never a row line,
    never in the W-L-P; the printed count and the JSON agree."""
    ex = tmp_path / "ex4"
    other = nfl_row(103, "Green Bay Packers", "Minnesota Vikings", "GB", "MIN", 0.45, 0.58, 0.56, 0.57, KO_1011,
                    qb_side="away", qb=["Jordan Love"])                     # the copy's match 103 is DET @ CHI
    other_would = nfl_row(104, "Denver Broncos", "Houston Texans", "DEN", "HOU", 0.45, 0.58, 0.56, 0.57, KO_1109,
                          qb_side="away", qb=["Bo Nix"])                    # the copy's match 104 is KC @ LV
    write_closing(ex, KO_1011 - timedelta(minutes=35),
                  annotated([cle_nyj(), bal_atl(), other], KO_1011, market_only=False), fam="NFL")
    write_closing(ex, KO_1018 - timedelta(minutes=35), annotated([lost_row()], KO_1018, market_only=False), fam="NFL")
    write_closing(ex, KO_1109 - timedelta(minutes=35),
                  annotated([sea_lar(), lost_would(), other_would], KO_1109, market_only=True), fam="NFL")
    _world(tmp_path / "w4.db", moved={102: KO_1011 + timedelta(days=1)})
    copy = _backup(tmp_path / "w4.db", tmp_path / "c4" / "nfl.db")
    rc, out = _run(capsys, "--db", copy, "--exports", ex)
    assert rc == 0, out
    nr = " · what was done: not read (no --ledger)"             # what was done on every row (231 item 2(c))
    labelled = {
        "  no result in this copy (unscored, counted): match 999 Miami Dolphins @ Buffalo Bills (PLAY)" + nr,
        "  teams differ (unscored, counted): match 103 Green Bay Packers @ Minnesota Vikings (PLAY; this database's "
        "match 103 is Detroit Lions @ Chicago Bears)" + nr,
        "  re-dated void (unscored, counted): match 102 Baltimore Ravens @ Atlanta Falcons (PLAY): void: re-dated "
        "2026-10-11 17:00Z → 2026-10-12 17:00Z" + nr,
        f"  no result in this copy (unscored, counted): match 998 New York Giants @ Philadelphia Eagles ({WOULD})" + nr,
        f"  teams differ (unscored, counted): match 104 Denver Broncos @ Houston Texans ({WOULD}; this database's "
        "match 104 is Kansas City Chiefs @ Las Vegas Raiders)" + nr}
    assert labelled <= set(out), sorted(labelled - set(out))
    assert len([ln for ln in out if "(unscored, counted): " in ln]) == 5
    rows = [ln for ln in out if ln.startswith("- ")]                       # the scored rows only: 101 and 105
    assert [re.search(r"\[match (\d+)\]", ln).group(1) for ln in rows] == ["101", "105"], rows
    assert (f"UNSCORED (counted toward thirty, labelled, never scored, outside the W-L-P, 225 item 3; per kind, never "
            f"pooled): PLAY — no result in this copy 1 · teams differ 1 · re-dated void 1 (re-dated 1 · placeholder "
            f"kickoff 0); {WOULD} — no result in this copy 1 · teams differ 1 · re-dated void 0 (re-dated 0 · "
            "placeholder kickoff 0)") in out
    count = [ln for ln in out if ln.startswith("COUNT toward thirty")]
    assert count == [f"{COUNT_HEAD}{UNBOUNDED}: 7 of 30 (PLAY 4 + {WOULD} 3) — {BELOW} · "
                     "PLAY W-L-P 0-1-0, void 0, open 0, unscored 3 (no result in this copy 1 · teams differ 1 · "
                     f"re-dated void 1) · {WOULD} W-L-P 0-0-0, void 0, open 1, unscored 2 (no result in this copy 1 · "
                     "teams differ 1 · re-dated void 0)"], count
    j = json.loads(out[-1][len("QB-HOLD-RECEIPT "):])
    assert j["unscored"] == {"play": {"no_result": 1, "teams": 1, "void": 1},
                             "would_be": {"no_result": 1, "teams": 1, "void": 0}}
    assert (j["play_rows"], j["would_be_rows"]) == (1, 1)                  # the scored rows, the W-L-P's
    assert j["play_record"] == {"win": 0, "loss": 1, "push": 0, "void": 0, "open": 0}
    assert j["would_be_record"] == {"win": 0, "loss": 0, "push": 0, "void": 0, "open": 1}
    assert (j["counted"], j["toward_thirty"], j["this_run_thirty_reached"]) == ({"play": 4, "would_be": 3}, 7, False)
    assert f": 7 of 30 (PLAY 4 + {WOULD} 3)" in count[0]                    # the printed count is the JSON's
    assert "thirty_reached" not in j                                        # renamed, no alias (232 item 2(a))


def test_a_copy_that_lacks_every_game_does_not_delay_the_read(capsys, tmp_path):
    """225 item 2(a): "A copy that lacks games must not delay the read that the count triggers." Thirty QB-flagged PLAY
    rows whose games the copy lacks are thirty: "thirty reached", every one labelled "no result in this copy", none
    scored."""
    ex = tmp_path / "ex5"
    rows = [nfl_row(900 + i, f"Away {i}", f"Home {i}", "AWY", "HME", 0.45, 0.58, 0.56, 0.57, KO_1011,
                    qb_side="away", qb=[f"QB {i}"]) for i in range(30)]
    write_closing(ex, KO_1011 - timedelta(minutes=35), annotated(rows, KO_1011, market_only=False), fam="NFL")
    _world(tmp_path / "w5.db")
    copy = _backup(tmp_path / "w5.db", tmp_path / "c5" / "nfl.db")
    rc, out = _run(capsys, "--db", copy, "--exports", ex)
    assert rc == 0, out
    count = [ln for ln in out if ln.startswith("COUNT toward thirty")]
    assert len(count) == 1 and (f"{UNBOUNDED}: 30 of 30 (PLAY 30 + {WOULD} 0) — this run's count alone reaches "
                                "thirty — for the architect's read (no verdict is computed here) · PLAY W-L-P 0-0-0, void 0, open 0, unscored 30 (no result "
                                "in this copy 30 · teams differ 0 · re-dated void 0)") in count[0], count
    assert len([ln for ln in out if ln.startswith("  no result in this copy (unscored, counted): match 9")]) == 30
    assert not [ln for ln in out if ln.startswith("- ")]
    j = json.loads(out[-1][len("QB-HOLD-RECEIPT "):])
    assert (j["toward_thirty"], j["this_run_thirty_reached"], j["play_rows"]) == (30, True, 0)


def test_the_count_line_says_thirty_reached_and_never_a_verdict():
    g = {"win": 0, "loss": 0, "push": 0, "void": 0, "open": 0}
    assert f"{UNBOUNDED}: 29 of 30 (PLAY 29 + {WOULD} 0) — {BELOW} · " in script.count_line(29, 0, g, g)
    line = script.count_line(25, 5, g, g)
    assert (f"{UNBOUNDED}: 30 of 30 (PLAY 25 + {WOULD} 5) — this run's count alone reaches thirty — for the "
            "architect's read (no verdict is computed here)") in line
    for w in ("PASS", "FAIL", "verdict:"):
        assert w not in line
    line = script.count_line(20, 10, g, g, {"no_result": 4, "teams": 1, "void": 1}, {"no_result": 2})
    assert f"30 of 30 (PLAY 20 + {WOULD} 10) — this run's count alone reaches thirty" in line
    assert ("PLAY W-L-P 0-0-0, void 0, open 0, unscored 6 (no result in this copy 4 · teams differ 1 · re-dated void 1)"
            in line), line
    assert line.endswith("unscored 2 (no result in this copy 2 · teams differ 0 · re-dated void 0)"), line


def test_read_only_the_copy_is_unchanged_and_no_sidecar_is_made(world, capsys):
    before = world["copy"].read_bytes()
    led_before = world["ledger"].read_bytes()
    rc, _ = _run(capsys, "--db", world["copy"], "--exports", world["ex"], "--ledger", world["ledger"])
    assert rc == 0
    assert world["copy"].read_bytes() == before and world["ledger"].read_bytes() == led_before
    assert sorted(p.name for p in world["copy"].parent.iterdir()) == ["nfl.db"]


# ---- the refusals --------------------------------------------------------------------------------------------------

def test_refusals(world, capsys, tmp_path):
    rc, out = _run(capsys, "--exports", world["ex"])
    assert rc == 2 and out[0].startswith("REFUSED: --db PATH is required")
    missing = tmp_path / "nowhere" / "nfl.db"
    rc, out = _run(capsys, "--db", missing, "--exports", world["ex"])
    assert rc == 2 and "no file at" in out[0] and not missing.exists() and not missing.parent.exists()
    under = ROOT / "data" / "qb-hold-never.db"
    rc, out = _run(capsys, "--db", under, "--exports", world["ex"])
    assert rc == 2 and "resolves under the repo's data/" in out[0] and not under.exists()
    side = world["copy"].with_name("nfl.db-wal")
    side.write_bytes(b"")
    rc, out = _run(capsys, "--db", world["copy"], "--exports", world["ex"])
    assert rc == 2 and "has a -wal sidecar" in out[0]
    side.unlink()
    rc, out = _run(capsys, "--db", world["copy"], "--exports", tmp_path / "no-exports")
    assert rc == 2 and out == [f"REFUSED: --exports {tmp_path / 'no-exports'}: not a directory; nothing read"]
    for bad, why in (("not json", "cannot read the ledger export"), ("[]", "no calls array"),
                     ('{"calls": [1]}', "a call is not an object"),
                     ('{"calls": [], "fills": {}}', "fills is not an array of objects")):
        p = tmp_path / "bad.json"
        p.write_text(bad)
        rc, out = _run(capsys, "--db", world["copy"], "--exports", world["ex"], "--ledger", p)
        assert rc == 2 and why in out[0] and len(out) == 1, (bad, out)
    blank = tmp_path / "blank" / "x.db"
    blank.parent.mkdir()
    con = sqlite3.connect(str(blank))
    con.execute("create table t (x int)")
    con.commit()
    con.close()
    rc, out = _run(capsys, "--db", blank, "--exports", world["ex"])
    assert rc == 2 and "cannot be read through a mode=ro + immutable=1 URI (no such table: matches)" in out[0], out
    thin = tmp_path / "thin" / "x.db"                 # a matches table, not the schema the read needs
    thin.parent.mkdir()
    con = sqlite3.connect(str(thin))
    con.execute("create table matches (id int)")
    con.commit()
    con.close()
    rc, out = _run(capsys, "--db", thin, "--exports", world["ex"])
    assert rc == 2 and "cannot be read as the schema the receipt needs (OperationalError" in out[0], out
    assert len(out) == 1


def test_the_data_refusal_is_the_repos_data_not_any_data(world, capsys, tmp_path):
    """The receipt of the docstring's wording (law 2): mlb_pitchers_gate.check_db refuses the repo's data/ (the
    checkout's, and the main checkout's from a worktree), by path or identity; a .backup copy under a directory named
    data elsewhere is read (still mode=ro&immutable=1, still unchanged)."""
    elsewhere = _backup(world["copy"], tmp_path / "data" / "nfl.db")
    before = elsewhere.read_bytes()
    rc, out = _run(capsys, "--db", elsewhere, "--exports", world["ex"])
    assert rc == 0, out
    assert elsewhere.read_bytes() == before and sorted(p.name for p in elsewhere.parent.iterdir()) == ["nfl.db"]
    doc = script.__doc__
    assert "under the repo's data/ (the checkout's, and the" in doc and "any data/" not in doc


# ---- 231 item 2(a)/(b): one machine's pair; host/ is read, the header names the directory and the copy read ----------

def _mirror(tmp_path, world):
    """The mirror's layout (deploy/hosting/exports_mirror.py): host/<date>/<file> and host/latest/<kind>.json. The 10-11
    and 10-18 runs in their dated folders; latest/ holds a copy of the newest (a row that would be counted twice, and
    one only it holds, never read); a folder not dated holds a file never read."""
    host = tmp_path / "mirror" / "host"
    a = write_closing(host / "2026-10-11", KO_1011 - timedelta(minutes=35),
                      annotated([cle_nyj(), bal_atl()], KO_1011, market_only=False), fam="NFL")
    b = write_closing(host / "2026-10-18", KO_1018 - timedelta(minutes=35),
                      annotated([kc_lv()], KO_1018, market_only=False), fam="NFL")
    (host / "latest").mkdir()
    (host / "latest" / "closing_NFL.json").write_text(b.read_text())
    write_closing(host / "latest", KO_1018 - timedelta(minutes=35),
                  annotated([lost_row()], KO_1018, market_only=False), fam="NFL")      # latest/ only: never read
    write_closing(host / "raw", KO_1011 - timedelta(minutes=35),
                  annotated([lost_row()], KO_1011, market_only=False), fam="NFL")      # not a dated folder: never read
    return host, a, b


def test_host_is_read_and_the_header_names_the_directory_and_the_copy(world, capsys, tmp_path):
    """231 item 2(a): "The "host/ is never read" refusal of round 1 is REMOVED: the header prints which directory and
    which copy were read, and my block pairs them". --exports the mirror's host/ tree reads host/<date>/closing_*.json
    (never latest/, never a folder that is not dated); the SOURCES line names the directory read (resolved, beside the
    path as given) and the copy read (resolved); the MACHINE-ERA line states the rule (the count toward thirty is the
    two runs' sum); nothing refuses the directory for its name."""
    host, _, _ = _mirror(tmp_path, world)
    rc, out = _run(capsys, "--db", world["copy"], "--exports", host, "--ledger", world["ledger"])
    assert rc == 0, out
    assert not [ln for ln in out if ln.startswith("REFUSED")]
    src = [ln for ln in out if ln.startswith("SOURCES")]
    assert len(src) == 1, out
    assert src[0].startswith("SOURCES (the two, 223 item 5(b); one machine's pair, 231 item 2(a)): the copy read "
                             f"{Path(world['copy']).resolve()} (--db; a .backup copy, opened mode=ro&immutable=1;"), src
    assert (f" · the closing-file directory read {host.resolve()} (--exports {host}; closing_*.json there and in its "
            "dated folders <YYYY-MM-DD>/ 2, never latest/; redated.closing_rows): 2 read, runs 2026-10-11 16:25Z to "
            "2026-10-18 19:30Z, NFL games 3") in src[0], src
    assert "never read" not in src[0] and "host/ never" not in "\n".join(out)
    era = [ln for ln in out if ln.startswith("MACHINE-ERA")]
    assert era == [script.MACHINE_ERA] and out.index(era[0]) == out.index(src[0]) + 1
    assert "the sum is the architect's arithmetic on the two consoles, stated on #446 (232 item 2(a))" in era[0]
    assert "two runs' counts' sum" not in era[0] and "exports/host/" in era[0]
    assert [re.search(r"\[match (\d+)\]", ln).group(1) for ln in out if ln.startswith("- ")] == ["101", "102", "104"]
    assert not [ln for ln in out if "Miami Dolphins" in ln]                  # latest/ and raw/ are never read
    j = json.loads(out[-1][len("QB-HOLD-RECEIPT "):])
    assert (j["exports"], j["exports_read"], j["dated_folders"], j["closing_files"]) == (str(host), str(host.resolve()),
                                                                                         2, 2)
    assert j["counted"] == {"play": 3, "would_be": 0}


def test_a_symlink_into_host_and_any_spelling_of_host_are_read(world, capsys, tmp_path):
    """231 item 2(b): "host/ is a legitimate source when paired with the host's copy. No refusal is built for it." A
    link to host/, a link NAMED host, and HOST/Host spellings are each read; the SOURCES line names the resolved
    directory, so a link shows where it led."""
    host, _, _ = _mirror(tmp_path, world)
    link = tmp_path / "looks-fine"
    link.symlink_to(host, target_is_directory=True)
    rc, out = _run(capsys, "--db", world["copy"], "--exports", link)
    assert rc == 0, out
    assert f"the closing-file directory read {host.resolve()} (--exports {link}; " in \
        [ln for ln in out if ln.startswith("SOURCES")][0]
    assert _line(out, "Cleveland Browns @ New York Jets")
    named = tmp_path / "links" / "host"
    named.parent.mkdir()
    named.symlink_to(world["ex"], target_is_directory=True)
    rc, out = _run(capsys, "--db", world["copy"], "--exports", named)
    assert rc == 0 and _line(out, "Seattle Seahawks @ Los Angeles Rams"), out
    assert f"directory read {Path(world['ex']).resolve()} (--exports {named}; " in \
        [ln for ln in out if ln.startswith("SOURCES")][0]
    for spelt in ("HOST", "Host"):
        upper = tmp_path / "cased" / spelt
        write_closing(upper, KO_1011 - timedelta(minutes=35), annotated([cle_nyj()], KO_1011, market_only=False),
                      fam="NFL")
        rc, out = _run(capsys, "--db", world["copy"], "--exports", upper)
        assert rc == 0 and _line(out, "Cleveland Browns @ New York Jets"), out


def test_a_file_name_in_two_dated_folders_is_named_on_the_sources_line(world, capsys, tmp_path):
    """A closing file copied into two dated folders is read from each (closing_rows is the one reader); the SOURCES
    line counts and names it, so "N read" is never silently two runs where there was one; the game is one row."""
    host, a, _ = _mirror(tmp_path, world)
    (host / "2026-10-12").mkdir()
    (host / "2026-10-12" / a.name).write_text(a.read_text())
    rc, out = _run(capsys, "--db", world["copy"], "--exports", host)
    assert rc == 0, out
    src = [ln for ln in out if ln.startswith("SOURCES")][0]
    assert f"dated folders <YYYY-MM-DD>/ 3, never latest/; redated.closing_rows): 3 read, " in src, src
    assert src.endswith(f" · names in more than one folder 1 (each copy read): {a.name}"), src
    assert len([ln for ln in out if ln.startswith("- ") and "Cleveland Browns" in ln]) == 1
    assert json.loads(out[-1][len("QB-HOLD-RECEIPT "):])["counted"] == {"play": 3, "would_be": 0}


# ---- 231 item 2(c): what was done on every row, scored or unscored -------------------------------------------------

def test_an_unscored_row_of_each_cause_carries_what_was_done_and_the_ledger_counts_every_row(capsys, tmp_path):
    """231 item 2(c): "positions() matches the ledger's fills to EVERY row the receipt holds, scored or not ... the label
    stays the ledger's; the LEDGER line drops "an unscored row is not matched to fills"". The world of 225 item 3's
    test (PLAY 101 scored; 999 the copy lacks, 103 teams differ, 102 re-dated; would-be 105 scored, 998 the copy lacks,
    104 teams differ), with a fill on the game of each unscored row of every cause: one by event ticker (999), one by
    the Cockpit's game matcher on the closing row's own teams and start (103: the copy's match 103 is another game),
    one on the re-dated game (102), one on a would-be row (998); 104 holds none. Each prints under the ledger's label,
    its five fields as held; the LEDGER line and the JSON count every row of a kind; no figure is printed."""
    ex = tmp_path / "ex7"
    other = nfl_row(103, "Green Bay Packers", "Minnesota Vikings", "GB", "MIN", 0.45, 0.58, 0.56, 0.57, KO_1011,
                    qb_side="away", qb=["Jordan Love"])
    other_would = nfl_row(104, "Denver Broncos", "Houston Texans", "DEN", "HOU", 0.45, 0.58, 0.56, 0.57, KO_1109,
                          qb_side="away", qb=["Bo Nix"])
    write_closing(ex, KO_1011 - timedelta(minutes=35),
                  annotated([cle_nyj(), bal_atl(), other], KO_1011, market_only=False), fam="NFL")
    write_closing(ex, KO_1018 - timedelta(minutes=35), annotated([lost_row()], KO_1018, market_only=False), fam="NFL")
    write_closing(ex, KO_1109 - timedelta(minutes=35),
                  annotated([sea_lar(), lost_would(), other_would], KO_1109, market_only=True), fam="NFL")
    _world(tmp_path / "w7.db", moved={102: KO_1011 + timedelta(days=1)})
    copy = _backup(tmp_path / "w7.db", tmp_path / "c7" / "nfl.db")
    fills = [_fill("f-mia", "KXNFLGAME-26OCT18MIABUF-MIA", "yes", "Miami wins — Buffalo"),
             _fill("f-gb", "KXNFLGAME-26OCT11GBMINX-GB", "yes", "Green Bay wins — Minnesota"),
             _fill("f-bal", "KXNFLGAME-26OCT11BALATL-BAL", "no", "Baltimore wins — Atlanta"),
             _fill("f-nyg", "KXNFLGAME-26NOV09NYGPHI-PHI", "yes", "Philadelphia wins — New York G", closed=False)]
    led = tmp_path / "led7.json"
    led.write_text(json.dumps({"calls": [], "fills": fills}))
    rc, out = _run(capsys, "--db", copy, "--exports", ex, "--ledger", led)
    assert rc == 0, out

    def held(f):
        return "fills: " + json.dumps({k: f[k] for k in ("ticker", "side", "title", "opened", "closed")},
                                      ensure_ascii=False)
    want = {
        "  no result in this copy (unscored, counted): match 999 Miami Dolphins @ Buffalo Bills (PLAY) · what was "
        f"done: {held(fills[0])}",
        "  teams differ (unscored, counted): match 103 Green Bay Packers @ Minnesota Vikings (PLAY; this database's "
        f"match 103 is Detroit Lions @ Chicago Bears) · what was done: {held(fills[1])}",
        "  re-dated void (unscored, counted): match 102 Baltimore Ravens @ Atlanta Falcons (PLAY): void: re-dated "
        f"2026-10-11 17:00Z → 2026-10-12 17:00Z · what was done: {held(fills[2])}",
        f"  no result in this copy (unscored, counted): match 998 New York Giants @ Philadelphia Eagles ({WOULD}) · "
        f"what was done: {held(fills[3])}",
        f"  teams differ (unscored, counted): match 104 Denver Broncos @ Houston Texans ({WOULD}; this database's "
        "match 104 is Kansas City Chiefs @ Las Vegas Raiders) · what was done: not established"}
    assert want <= set(out), sorted(want - set(out))
    assert _line(out, "Cleveland Browns @ New York Jets").endswith("what was done: not established")
    assert ("LEDGER: NFL game fills entries read 4 · fitting more than one row (ambiguous, given to none) 0 · PLAY rows "
            f"(scored + unscored) with fills on the game 3 of 4 · {WOULD} rows (scored + unscored) with fills on the game "
            "1 of 3") in out
    j = json.loads(out[-1][len("QB-HOLD-RECEIPT "):])
    assert j["what_was_done"] == {"play": {"fills": 3, "not_established": 1},
                                  "would_be": {"fills": 1, "not_established": 2}}
    for k in ("play", "would_be"):                         # the LEDGER denominators are the kind's count toward thirty
        assert sum(j["what_was_done"][k].values()) == j["counted"][k]
    assert j["play_record"] == {"win": 0, "loss": 1, "push": 0, "void": 0, "open": 0}     # the W-L-P is unchanged
    body = "\n".join(ln for ln in out if not ln.startswith(("RULING", "SOURCES", "WHAT WAS DONE FROM")))
    for fig in FILL_FIGURES + ("f-mia", "f-gb", "f-bal", "f-nyg"):
        assert fig not in body, fig
    for key in ("qty", "entry", "exit", "staked", "fees", "pnl_net", "id"):
        assert f'"{key}"' not in body, key


def test_a_fill_fitting_a_scored_and_an_unscored_row_is_ambiguous(world, capsys, tmp_path):
    """Matching every row widens the matcher's candidates: a fill with no event the rows name, fitting a scored row and
    an unscored row of the same teams and day by the game matcher, is ambiguous, given to none (refusals stay
    refusals), never to the scored row by default."""
    rows = annotated([cle_nyj()], KO_1011, market_only=False)
    twin = json.loads(json.dumps(rows[0]))
    twin["match_id"] = 997                                                  # the copy lacks it: unscored
    write_closing(tmp_path / "ex8", KO_1011 - timedelta(minutes=35), rows + [twin], fam="NFL")
    led = tmp_path / "led8.json"
    led.write_text(json.dumps({"calls": [], "fills": [_fill("f", "KXNFLGAME-26OCT11CLENYJX-CLE", "yes",
                                                            "Cleveland wins — New York J")]}))
    rc, out = _run(capsys, "--db", world["copy"], "--exports", tmp_path / "ex8", "--ledger", led)
    assert rc == 0, out
    assert ("LEDGER: NFL game fills entries read 1 · fitting more than one row (ambiguous, given to none) 1 · PLAY rows "
            f"(scored + unscored) with fills on the game 0 of 2 · {WOULD} rows (scored + unscored) with fills on the game "
            "0 of 0") in out
    assert "match 997 Cleveland Browns @ New York Jets (PLAY) · what was done: not established" in "\n".join(out)


# ---- the review findings (Codex P2s): a figure in a printed field refused, every entry its own ----------------------

@pytest.mark.parametrize("field,value", [("title", {"qty": 137, "price": 0.43}), ("side", ["yes", 137]),
                                         ("opened", 137), ("closed", True), ("ticker", 137.5)])
def test_a_fill_whose_printed_field_is_not_a_string_is_refused_never_echoed(world, capsys, tmp_path, field, value):
    """A fill's ticker, side, title, opened and closed are the Cockpit export's strings or null (tools/cockpit.html
    importKalshiCSV: the CSV's cells): any other value there would be printed by "what was done", figures with it. The
    ledger is refused, nothing read, the field named and the value never echoed."""
    bad = _fill("f-lv", "KXNFLGAME-26OCT18KCLV-LV", "yes", "Las Vegas wins — Kansas City")
    bad[field] = value
    led = tmp_path / "led-obj.json"
    led.write_text(json.dumps({**LEDGER, "fills": [bad]}))
    rc, out = _run(capsys, "--db", world["copy"], "--exports", world["ex"], "--ledger", led)
    assert rc == 2 and out == [f"REFUSED: --ledger {led}: a fill's {field} is not a string or null (the value is not "
                               "printed); nothing read"], out
    said = out[0].replace(str(led), "")
    assert "137" not in said and "0.43" not in said, said
    ok = {**_fill("f-x", "KXNFLGAME-26OCT18KCLV-LV", "yes", None, closed=False)}     # null stays readable
    led.write_text(json.dumps({**LEDGER, "fills": [ok]}))
    rc, out = _run(capsys, "--db", world["copy"], "--exports", world["ex"], "--ledger", led)
    assert rc == 0, out


def test_split_fills_on_one_game_print_as_their_own_entries_and_one_id_prints_once(world, capsys, tmp_path):
    """Two entries on the same game whose printed fields match and whose hidden fields (id, qty, price, fee) differ are
    two entries: each prints, agreeing with the entries read; no quantity or price of either reaches the output. The
    same entry (the same id) twice prints once; an entry with no id is never deduped."""
    a = _fill("f-lv-1", "KXNFLGAME-26OCT18KCLV-LV", "yes", "Las Vegas wins — Kansas City")
    b = {**a, "id": "f-lv-2", "qty": 641, "entry": 0.5517, "staked": 353.64, "fees": 2.71, "pnl_net": 284.22}
    held = '{"ticker": "KXNFLGAME-26OCT18KCLV-LV", "side": "yes", "title": "Las Vegas wins — Kansas City", ' \
           '"opened": "2026-10-18T19:31:00Z", "closed": "2026-10-19T00:10:00Z"}'
    led = tmp_path / "led-split.json"
    led.write_text(json.dumps({**LEDGER, "fills": [a, b]}))
    rc, out = _run(capsys, "--db", world["copy"], "--exports", world["ex"], "--ledger", led)
    assert rc == 0, out
    kc = _line(out, "Kansas City Chiefs @ Las Vegas Raiders")
    assert kc.endswith(f"what was done: fills: {held}; {held}"), kc
    assert [ln for ln in out if ln.startswith("LEDGER:")][0].startswith("LEDGER: NFL game fills entries read 2 · ")
    body = "\n".join(ln for ln in out if not ln.startswith(("RULING", "SOURCES", "WHAT WAS DONE FROM")))
    for fig in FILL_FIGURES + ("641", "0.5517", "353.64", "2.71", "284.22", "f-lv-1", "f-lv-2"):
        assert fig not in body, fig
    led.write_text(json.dumps({**LEDGER, "fills": [a, dict(a)]}))                     # the same entry twice
    rc, out = _run(capsys, "--db", world["copy"], "--exports", world["ex"], "--ledger", led)
    assert rc == 0
    assert _line(out, "Kansas City Chiefs @ Las Vegas Raiders").endswith(f"what was done: fills: {held}")
    assert [ln for ln in out if ln.startswith("LEDGER:")][0].startswith("LEDGER: NFL game fills entries read 1 · ")
    no_id = {k: v for k, v in a.items() if k != "id"}                                # no id: never deduped
    led.write_text(json.dumps({**LEDGER, "fills": [no_id, dict(no_id)]}))
    rc, out = _run(capsys, "--db", world["copy"], "--exports", world["ex"], "--ledger", led)
    assert rc == 0
    assert _line(out, "Kansas City Chiefs @ Las Vegas Raiders").endswith(f"what was done: fills: {held}; {held}")


# ---- 232 item 2: one run's count, under its era's bound; --from / --through on the closing run's start, UTC --------

BOUNDARY = "2026-10-26T12:00:00Z"                  # 232 item 2(b): the closing run's start instant, UTC
KO_SNF = datetime(2026, 10, 26, 0, 20)             # KC@SEA, SNF 10-25 ET
RUN_SNF = datetime(2026, 10, 25, 23, 45)           # "the closing run started 2026-10-25 ~23:45Z"
KO_EDGE = datetime(2026, 10, 26, 12, 35)
RUN_EDGE = datetime(2026, 10, 26, 12, 0)           # a run start exactly at the bound: the host era's
KO_MNF = datetime(2026, 10, 27, 0, 15)             # MNF 10-26 ET: the host's first closing as writer of record
RUN_MNF = datetime(2026, 10, 26, 23, 40)
ERA_GAMES = ((106, "Kansas City Chiefs", "Seattle Seahawks", KO_SNF, 27, 20),
             (107, "New York Giants", "Washington Commanders", KO_MNF, 13, 24),
             (108, "Denver Broncos", "Houston Texans", KO_EDGE, 17, 10),
             (109, "Tennessee Titans", "Indianapolis Colts", KO_MNF, 9, 31))


def _qb_play(mid, away, home, ko):
    ca, ch = away.split()[0][:3].upper(), home.split()[0][:3].upper()
    return nfl_row(mid, away, home, ca, ch, 0.45, 0.58, 0.56, 0.57, ko, qb_side="away", qb=[f"QB {mid}"])


def _era_world(tmp_path):
    """KC@SEA (232 item 2(b)): the laptop's closing of it (run 2026-10-25 23:45Z) in the laptop's own exports/; the
    host's pull, exports/host/ (flat, pull_exports.py), holding the host's rehearsal closing of the same game (the same
    run start), a run started exactly at the bound (108), the MNF run (107) and a closing file with no run start (109:
    no closing block start, no stamp in its name). Each row a QB-flagged PLAY."""
    g = {mid: (away, home, ko) for mid, away, home, ko, _, _ in ERA_GAMES}
    lap = tmp_path / "laptop" / "exports"
    write_closing(lap, RUN_SNF, annotated([_qb_play(106, *g[106])], KO_SNF, market_only=False), fam="NFL")
    host = tmp_path / "laptop" / "exports" / "host"         # the laptop's pull: a subfolder, never a dated one
    write_closing(host, RUN_SNF, annotated([_qb_play(106, *g[106])], KO_SNF, market_only=False), fam="NFL")
    write_closing(host, RUN_EDGE, annotated([_qb_play(108, *g[108])], KO_EDGE, market_only=False), fam="NFL")
    write_closing(host, RUN_MNF, annotated([_qb_play(107, *g[107])], KO_MNF, market_only=False), fam="NFL")
    p = write_closing(tmp_path / "scratch", RUN_MNF, annotated([_qb_play(109, *g[109])], KO_MNF, market_only=False),
                      fam="NFL")
    doc = json.loads(p.read_text())
    del doc["closing"]["start"]
    (host / "closing_NFL_manual.json").write_text(json.dumps(doc))   # no start, no stamp: the run start unknown
    _world(tmp_path / "era.db", extra=ERA_GAMES)
    copy = _backup(tmp_path / "era.db", tmp_path / "era-copy" / "nfl.db")
    return lap, host, copy


def _matches(out):
    return [re.search(r"\[match (\d+)\]", ln).group(1) for ln in out if ln.startswith("- ")]


def test_kc_sea_is_the_laptops_row_and_the_hosts_rehearsal_is_excluded_by_the_bound(capsys, tmp_path):
    """232 item 2(b): "KC@SEA (SNF 10-25 ET; the closing run started 2026-10-25 ~23:45Z) is the LAPTOP's row and only
    the laptop's; the host's rehearsal closing of it is not a record and is excluded by the bound, not by hand." The
    laptop run (--through the boundary) counts it; the host run (--from the boundary, on exports/host/) does not, and
    names the exclusion; each console prints ONE run's count under its era's label, exactly as ruled (232 item 2(a))."""
    lap, host, copy = _era_world(tmp_path)
    rc, out = _run(capsys, "--db", copy, "--exports", lap, "--through", BOUNDARY)
    assert rc == 0, out
    assert _matches(out) == ["106"]                                    # the laptop's row; its host/ never read
    count = [ln for ln in out if ln.startswith("COUNT toward thirty")]
    assert len(count) == 1 and f"): laptop era, runs through {BOUNDARY}: 1 of 30 (PLAY 1 + {WOULD} 0) — " in count[0]
    bound = [ln for ln in out if ln.startswith("BOUND")]
    assert bound == [f"BOUND (232 item 2(b); the closing run's start instant, UTC; --from inclusive, --through "
                     f"exclusive: a run start exactly at the bound is the host era's): this run: laptop era, runs "
                     f"through {BOUNDARY} · --from — · --through {BOUNDARY} · excluded by the bound (not counted, not "
                     "read for any game): NFL closing rows 0, from 0 run(s) (closing files 0), NFL games left with no row "
                     "in the bound 0, of this receipt (named below) 0"], bound
    j = json.loads(out[-1][len("QB-HOLD-RECEIPT "):])
    assert j["run"] == {"era": "laptop", "label": f"laptop era, runs through {BOUNDARY}", "from": None,
                        "through": BOUNDARY}
    assert (j["toward_thirty"], j["this_run_thirty_reached"]) == (1, False) and "thirty_reached" not in j

    rc, out = _run(capsys, "--db", copy, "--exports", host, "--from", BOUNDARY)
    assert rc == 0, out
    assert _matches(out) == ["108", "107"]                             # the edge run (at the bound) and MNF
    assert not [ln for ln in out if ln.startswith("- ") and "Kansas City Chiefs" in ln]
    assert ("  outside the bound (not counted): match 106 Kansas City Chiefs @ Seattle Seahawks (PLAY, run 2026-10-25 "
            "23:45Z)") in out
    count = [ln for ln in out if ln.startswith("COUNT toward thirty")]
    assert len(count) == 1 and f"): host era, runs from {BOUNDARY}: 2 of 30 (PLAY 2 + {WOULD} 0) — " in count[0]
    bound = [ln for ln in out if ln.startswith("BOUND")][0]
    assert bound.endswith(f"this run: host era, runs from {BOUNDARY} · --from {BOUNDARY} · --through — · excluded by "
                          "the bound (not counted, not read for any game): NFL closing rows 1, from 1 run(s) "
                          "(closing files 1), NFL games left with no row in the bound 1, of this receipt (named "
                          "below) 1"), bound
    src = [ln for ln in out if ln.startswith("SOURCES")][0]           # the span the bound kept, beside every file's
    assert ("runs of every file read (before the bound) 2026-10-25 23:45Z to 2026-10-26 23:40Z, runs in the bound "
            "2026-10-26 12:00Z to 2026-10-26 23:40Z, NFL games 2") in src, src
    assert out.index(bound) == out.index([ln for ln in out if ln.startswith("MACHINE-ERA")][0]) + 1   # the header
    j = json.loads(out[-1][len("QB-HOLD-RECEIPT "):])
    assert j["run"] == {"era": "host", "label": f"host era, runs from {BOUNDARY}", "from": BOUNDARY, "through": None}
    assert j["excluded_by_bound"] == {"runs": 1, "closing_files": 1, "nfl_closing_rows": 1, "nfl_games": 1,
                                      "named": {"play": 1, "would_be": 0}}
    assert (j["toward_thirty"], j["this_run_thirty_reached"]) == (2, False)


def test_a_run_start_exactly_at_the_bound_is_the_host_eras(capsys, tmp_path):
    """232 item 2(b): "a run start exactly at the bound belongs to the host era": --from is inclusive, --through
    exclusive. The run started at 2026-10-26T12:00:00Z is counted by --from and excluded (named) by --through."""
    _, host, copy = _era_world(tmp_path)
    rc, out = _run(capsys, "--db", copy, "--exports", host, "--from", BOUNDARY)
    assert rc == 0 and "108" in _matches(out), out
    rc, out = _run(capsys, "--db", copy, "--exports", host, "--through", BOUNDARY)
    assert rc == 0, out
    assert "108" not in _matches(out) and "107" not in _matches(out)
    assert ("  outside the bound (not counted): match 108 Denver Broncos @ Houston Texans (PLAY, run 2026-10-26 "
            "12:00Z)") in out
    j = json.loads(out[-1][len("QB-HOLD-RECEIPT "):])
    assert j["excluded_by_bound"]["runs"] == 2 and j["excluded_by_bound"]["named"] == {"play": 2, "would_be": 0}


def test_a_window_and_the_unbounded_run_are_labelled_by_their_bounds(capsys, tmp_path):
    """Both bounds: a window, labelled with both and with no era; neither: the unbounded run, no era, every run read
    (the conservative labels of #810's build: the label is the bound's, never a machine's)."""
    _, host, copy = _era_world(tmp_path)
    rc, out = _run(capsys, "--db", copy, "--exports", host, "--from", BOUNDARY, "--through", "2026-10-26T20:00:00Z")
    assert rc == 0, out
    assert _matches(out) == ["108"]
    label = f"window, runs from {BOUNDARY} through 2026-10-26T20:00:00Z (no era: a window is neither era's run)"
    assert f"): {label}: 1 of 30 (PLAY 1 + " in [ln for ln in out if ln.startswith("COUNT toward thirty")][0]
    assert json.loads(out[-1][len("QB-HOLD-RECEIPT "):])["run"]["era"] == "window"
    rc, out = _run(capsys, "--db", copy, "--exports", host)
    assert rc == 0, out
    assert sorted(_matches(out)) == ["106", "107", "108", "109"]       # no bound: every run read, the unknown one too
    assert [ln for ln in out if ln.startswith("BOUND")][0].endswith(" · no bound: every run read, nothing excluded")
    assert not [ln for ln in out if ln.startswith("RUN START UNKNOWN")]
    assert f"): {UNBOUNDED}: 4 of 30 (PLAY 4 + " in [ln for ln in out if ln.startswith("COUNT toward thirty")][0]
    j = json.loads(out[-1][len("QB-HOLD-RECEIPT "):])
    assert (j["run"]["era"], j["excluded_by_bound"], j["run_start_unknown"]) == ("unbounded", None, None)


def test_a_row_with_no_run_start_is_outside_every_bound_and_named(capsys, tmp_path):
    """A closing row with no run start (no closing block start, no stamp in the file name) cannot be placed in an era
    (law 4): a bounded run excludes it, counts it on its own RUN START UNKNOWN line and names its game; never counted."""
    _, host, copy = _era_world(tmp_path)
    for flag in ("--from", "--through"):
        rc, out = _run(capsys, "--db", copy, "--exports", host, flag, BOUNDARY)
        assert rc == 0, out
        assert "109" not in _matches(out)
        assert ("RUN START UNKNOWN, OUTSIDE EVERY BOUND (232 item 2(b); law 4: a row with no run start is never placed "
                "in an era; not counted): NFL closing rows 1 (closing files 1), NFL games left with no row in the bound "
                "1, of this receipt (named below) 1") in out, out
        assert ("  run start unknown, outside every bound (not counted): match 109 Tennessee Titans @ Indianapolis "
                "Colts (PLAY, run start unknown)") in out
        j = json.loads(out[-1][len("QB-HOLD-RECEIPT "):])
        assert j["run_start_unknown"] == {"runs": None, "closing_files": 1, "nfl_closing_rows": 1, "nfl_games": 1,
                                          "named": {"play": 1, "would_be": 0}}


@pytest.mark.parametrize("bad", ["2026-10-26", "2026-10-26T12:00:00", "2026-10-26T12:00:00+00:00",
                                 "2026-10-26 12:00:00Z", "2026-10-26T12:00Z", "2026-13-26T12:00:00Z",
                                 "2026-10-26T12:00:00.000Z", "2026-10-26t12:00:00z", "",
                                 "\uff12\uff10\uff12\uff16-10-26T12:00:00Z",      # fullwidth digits: ASCII only
                                 "\u0662\u0660\u0662\u0666-10-26T12:00:00Z"])     # Arabic-Indic digits
def test_a_malformed_instant_is_refused_nothing_read(world, capsys, bad):
    for flag in ("--from", "--through"):
        rc, out = _run(capsys, "--db", world["copy"], "--exports", world["ex"], flag, bad)
        assert rc == 2 and out == [f"REFUSED: {flag} {bad!r}: not a UTC instant YYYY-MM-DDTHH:MM:SSZ (232 item 2(b)); "
                                   "nothing read"], out


def test_a_window_holding_no_instant_is_refused(world, capsys):
    for lo, hi in ((BOUNDARY, BOUNDARY), ("2026-10-27T00:00:00Z", BOUNDARY)):
        rc, out = _run(capsys, "--db", world["copy"], "--exports", world["ex"], "--from", lo, "--through", hi)
        assert rc == 2 and out == [f"REFUSED: --from {lo} is not before --through {hi}: the window holds no run start "
                                   "(232 item 2(b)); nothing read"], out


def test_no_option_takes_another_runs_count():
    """232 item 2(a): "the script takes NO other run's count as an input"."""
    opts = {a for a in script.main.__code__.co_consts if isinstance(a, str) and a.startswith("--")}
    assert opts >= {"--db", "--exports", "--from", "--through", "--ledger"}
    assert not [o for o in opts if re.search(r"count|sum|other|prior|previous|laptop|host", o)], opts


# ---- the fill entry as the Cockpit's export holds it (#811, addendum 233 item 1) -------------------------------------

COCKPIT = ROOT / "tools" / "cockpit.html"
# Kalshi's confirmed CSV header (tools/cockpit.html, the comment above mapHeaders), the columns importKalshiCSV maps
KALSHI_HDR = ("subtrader_id", "type", "quantity_fp", "market_ticker", "side", "entry_price_dollars", "exit_price_dollars",
              "open_fees_dollars", "close_fees_dollars", "realized_pnl_without_fees_dollars",
              "realized_pnl_with_fees_dollars", "close_timestamp", "open_timestamp", "product", "period_start",
              "market_title")
IMPORT_KEYS = ("id", "ticker", "side", "qty", "entry", "exit", "staked", "fees", "open_fee", "close_fee", "pnl_pre",
               "pnl_net", "opened", "closed", "title")                      # importKalshiCSV's fx literal, in order
PARSE_KEYS = ("kind", "family", "sports", "date", "teams", "sideCode", "start")  # parseTicker's sport result
SIDE_KEYS = ("backed", "backed_role", "teams_title", "resolve_note", "resolved_via", "no_on", "no_on_role", "composite")
# the synthetic CSV cells' figures (quantity, entry, fee, P&L) and the stake the import computes: never printed
CSV_FIGURES = ("2113", "0.3719", "4.0817", "73.6911", "69.6094", "785.8247")
KO_1101 = datetime(2026, 11, 1, 18, 0)         # 13:00 ET: Baltimore @ Buffalo, the finding's game (match 15149)


def _csv_cells(ticker, side, title, opened, exit_="1"):
    return ["sub-s1", "trade", "2113", ticker, side, "0.3719", exit_, "4.0817", "0", "73.6911", "69.6094",
            "2026-11-01T21:30:00Z", opened, "sports", "2026-11-01", title]


def _cockpit_entry(cells):
    """The entry the Cockpit's importKalshiCSV stores for one CSV row of KALSHI_HDR (tools/cockpit.html), the shape
    "Export ledger (JSON)" writes as held: the fx literal, parseTicker's fields spread in, sideFields' for a sport
    ticker. Synthetic figures only. test_the_fixture_is_the_cockpits_import_shape pins it to the Cockpit's own output."""
    from src.walters import ledger_fills as lf
    g = dict(zip(KALSHI_HDR, cells))
    num = float
    qty, entry, of, cf, pre, net = (num(g[k]) for k in ("quantity_fp", "entry_price_dollars", "open_fees_dollars",
                                                         "close_fees_dollars", "realized_pnl_without_fees_dollars",
                                                         "realized_pnl_with_fees_dollars"))
    fx = {"id": "\u241f".join(cells), "ticker": g["market_ticker"], "side": g["side"], "qty": qty, "entry": entry,
          "exit": num(g["exit_price_dollars"]), "staked": round(qty * entry, 4), "fees": round(of + cf, 4),
          "open_fee": of, "close_fee": cf, "pnl_pre": pre, "pnl_net": net, "opened": g["open_timestamp"],
          "closed": g["close_timestamp"], "title": g["market_title"]}
    p = lf.parse_ticker(fx["ticker"])
    fx.update(p)
    if p["kind"] == "sport":
        fx.update(lf.side_fields(p, fx["title"], fx["side"]))
    return fx


BUF_CELLS = _csv_cells("KXNFLGAME-26NOV01BALBUF-BUF", "yes", "Buffalo wins — Baltimore", "2026-11-01T17:20:00Z")
# the entry the Cockpit's own importKalshiCSV stored for BUF_CELLS (its functions run in node on the synthetic row,
# 2026-11-03; the PR body pastes that node run's output, synthetic values only), the id left out (it is the cells joined by U+241F)
BUF_ENTRY = {"ticker": "KXNFLGAME-26NOV01BALBUF-BUF", "side": "yes", "qty": 2113, "entry": 0.3719, "exit": 1,
             "staked": 785.8247, "fees": 4.0817, "open_fee": 4.0817, "close_fee": 0, "pnl_pre": 73.6911,
             "pnl_net": 69.6094, "opened": "2026-11-01T17:20:00Z", "closed": "2026-11-01T21:30:00Z",
             "title": "Buffalo wins — Baltimore", "kind": "sport", "family": "NFL", "sports": ["NFL"],
             "date": "2026-11-01", "teams": "BALBUF", "sideCode": "BUF", "start": None, "backed": "Buffalo",
             "backed_role": "HOME", "teams_title": ["Buffalo", "Baltimore"], "resolve_note": None,
             "resolved_via": "ticker", "no_on": None, "no_on_role": None, "composite": False}
# an EVENT ticker in the ticker column (no -SIDE): the Cockpit stores it as no sport market at all
EVENT_ONLY_CELLS = _csv_cells("KXNFLGAME-26NOV01BALBUF", "yes", "Buffalo wins — Baltimore", "2026-11-01T17:23:00Z")
EVENT_ONLY_ENTRY = {**{k: BUF_ENTRY[k] for k in IMPORT_KEYS if k != "id"}, "ticker": "KXNFLGAME-26NOV01BALBUF",
                    "opened": "2026-11-01T17:23:00Z", "kind": "non_sport",
                    "category": "non-sport / unrecognised market"}


def _js_keys(literal: str) -> list[str]:
    """The key names of a JS object literal's top level (shorthand `id` and `k:v` alike; a spread is left out; a `//`
    comment dropped)."""
    parts, depth, cur = [], 0, ""
    for ch in re.sub(r"//[^\n]*", "", literal).strip()[1:-1]:          # a line comment is not a key
        depth += ch in "([{"
        depth -= ch in ")]}"
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.split(":")[0].strip() for p in parts if p.strip() and not p.strip().startswith("...")]


def test_the_fixture_is_the_cockpits_import_shape():
    """Law 1, from the code (addendum 233 item 1): the Cockpit's "Export ledger (JSON)" writes loadLedger() as held,
    every fills entry is what importKalshiCSV stored: the fx literal's keys, `ticker` from the first header holding
    "ticker" but not "event" (market_ticker: the MARKET ticker), `opened`/`closed` the raw open/close timestamps, the
    date only in the ticker (parseTicker), sideFields' keys for a sport ticker. The fixture is that shape exactly."""
    html = COCKPIT.read_text()
    assert 'new Blob([JSON.stringify(loadLedger(),null,1)]' in html               # the export: the ledger as held
    imp = html[html.index("function importKalshiCSV("):html.index("function mveLegs(")]
    lit = re.search(r"const fx=(\{.*?\.\.\.p\});", imp, re.S).group(1)
    assert _js_keys(lit) == list(IMPORT_KEYS), _js_keys(lit)
    for want in ('ticker:g(r,"ticker")', 'side:g(r,"side")', 'opened:g(r,"openTs")', 'closed:g(r,"closeTs")',
                 'title:g(r,"title")', "const id=r.join(\"\\u241f\")"):
        assert want in imp, want
    assert 'ticker:find(h=>has(h,"ticker")&&!has(h,"event"))' in html            # the market ticker, never the event's
    sf = html[html.index("function sideFields("):html.index("function importKalshiCSV(")]
    assert _js_keys(re.search(r"return (\{.*?\});", sf, re.S).group(1)) == list(SIDE_KEYS)
    pt = html[html.index("function parseTicker("):html.index("function etOffsetMs(")]
    assert _js_keys(re.search(r'return (\{kind:"sport".*?\});', pt, re.S).group(1)) == list(PARSE_KEYS)
    got = _cockpit_entry(BUF_CELLS)
    assert list(got) == list(IMPORT_KEYS + PARSE_KEYS + SIDE_KEYS)
    assert got["id"] == "\u241f".join(BUF_CELLS) and {k: v for k, v in got.items() if k != "id"} == BUF_ENTRY
    ev = _cockpit_entry(EVENT_ONLY_CELLS)
    assert {k: v for k, v in ev.items() if k != "id"} == EVENT_ONLY_ENTRY


def _rows_1101(events=True, names=("Buffalo Bills", "Baltimore Ravens")):
    return [{"key": 15149, "home": names[0], "away": names[1], "kickoff_iso": "2026-11-01T18:00:00",
             "events": {"KXNFLGAME-26NOV01BALBUF"} if events else set()}]


def _held(f):
    return {k: f[k] for k in script.LEDGER_FIELDS}


def test_the_buf_shaped_entry_matches_by_event_ticker():
    """233 item 1: "the BUF-shaped case matches by event ticker". The entry exactly as the export holds it (the market
    ticker KXNFLGAME-26NOV01BALBUF-BUF); its event, the ticker less its side, is the event the closing row's order and
    Kalshi legs name. Matched on the event alone: with teams the game matcher could never fit, it is still the row's;
    with no event on the row and those teams, it is no row's (so the event did it)."""
    f = _cockpit_entry(BUF_CELLS)
    L = {"calls": [], "fills": [f]}
    pos = script.positions(L, _rows_1101(names=("Synthetic Home", "Synthetic Away")))
    assert pos["by_row"] == {15149: [_held(f)]} and pos["ambiguous"] == 0 and pos["nfl_fills"] == 1
    pos = script.positions(L, _rows_1101(events=False, names=("Synthetic Home", "Synthetic Away")))
    assert pos["by_row"] == {} and pos["ambiguous"] == 0 and pos["nfl_fills"] == 1


def test_a_csv_imported_entry_matches_by_the_cockpits_game_matcher():
    """233 item 1: "a CSV-imported fill matches by the Cockpit's game matcher". With no event on the row (a closing
    row whose legs carry no ticker), the entry fits the row's full names by the ticker's codes (codesFit: BAL ~
    Baltimore Ravens, BUF ~ Buffalo Bills) within a day of the ticker's own date, the only date a CSV-imported entry
    carries; the same with a ticker carrying the ET start (HHMM: startNearest within 3h), whose event the row never
    names. opened/closed are read by no matcher: an entry whose opened is another day still matches."""
    f = _cockpit_entry(BUF_CELLS)
    hhmm = _cockpit_entry(_csv_cells("KXNFLGAME-26NOV011300BALBUF-BUF", "yes", "Buffalo wins — Baltimore",
                                     "2026-11-01T17:21:00Z"))
    assert hhmm["start"] == "2026-11-01T18:00:00"
    late = _cockpit_entry(_csv_cells("KXNFLGAME-26NOV01BALBUF-BAL", "no", "Baltimore wins — Buffalo",
                                     "2026-10-29T15:00:00Z"))
    for title in ("Buffalo wins — Baltimore", "Baltimore at Buffalo Winner?", None):
        g = {**f, "title": title, "id": f"{f['id']}|{title}"}
        pos = script.positions({"calls": [], "fills": [g]}, _rows_1101(events=False))
        assert pos["by_row"] == {15149: [_held(g)]}, title
    pos = script.positions({"calls": [], "fills": [f, hhmm, late]}, _rows_1101(events=False))
    assert pos["by_row"] == {15149: [_held(f), _held(hhmm), _held(late)]} and pos["ambiguous"] == 0
    pos = script.positions({"calls": [], "fills": [hhmm]}, _rows_1101(events=True))   # event differs: the matcher
    assert pos["by_row"] == {15149: [_held(hhmm)]}


def test_an_entry_on_another_game_does_not_match_and_ambiguity_is_still_refused():
    """Another game the same day (Miami @ New England), the same teams a week earlier, an event ticker with no side
    and another NFL series are no row's; the event-only and spread entries are not NFL game entries at all (the
    Cockpit's parseTicker is the rule). Two rows of the same teams and day with no event: ambiguous, given to none."""
    f = _cockpit_entry(BUF_CELLS)
    others = [_cockpit_entry(_csv_cells("KXNFLGAME-26NOV01MIANE-NE", "no", "New England wins — Miami",
                                        "2026-11-01T17:22:00Z", exit_="0")),
              _cockpit_entry(_csv_cells("KXNFLGAME-26OCT25BALBUF-BUF", "yes", "Buffalo wins — Baltimore",
                                        "2026-10-25T17:20:00Z")),
              _cockpit_entry(EVENT_ONLY_CELLS),
              _cockpit_entry(_csv_cells("KXNFLSPREAD-26NOV01BALBUF-BUF3", "yes", "Buffalo wins by more than three?",
                                        "2026-11-01T17:24:00Z")),
              _cockpit_entry(_csv_cells("KXMLBGAME-26OCT18NYYBOS-BOS", "yes", "Boston wins — New York Y",
                                        "2026-10-18T17:20:00Z"))]
    pos = script.positions({"calls": [], "fills": others}, _rows_1101())
    assert pos["by_row"] == {} and pos["ambiguous"] == 0 and pos["nfl_fills"] == 2
    twins = _rows_1101(events=False) + [{**_rows_1101(events=False)[0], "key": 15150}]
    pos = script.positions({"calls": [], "fills": [f]}, twins)
    assert pos["by_row"] == {} and pos["ambiguous"] == 1
    twins = _rows_1101() + [{**_rows_1101()[0], "key": 15150}]                       # the event on both: refused too
    pos = script.positions({"calls": [], "fills": [f]}, twins)
    assert pos["by_row"] == {} and pos["ambiguous"] == 1


def test_the_receipt_reads_a_cockpit_export_and_prints_no_figure(capsys, tmp_path):
    """End to end on a bd_ledger_v1 export in exactly the Cockpit's shape (meta, calls, fills as importKalshiCSV stored
    them; synthetic figures): Baltimore @ Buffalo (match 15149, a QB-flagged PLAY HOME) prints its entries under the
    ledger's own label, the BUF market-ticker entry and the HHMM one (by the game matcher); the LEDGER line counts
    the four NFL game entries (the event-only and spread entries are none). Without --unmatched no new line is
    printed (235 item 2(c): the diagnostic is behind its flag). No quantity, price, fee, stake, P&L or id is printed."""
    ex = tmp_path / "ex11"
    buf = nfl_row(15149, "Baltimore Ravens", "Buffalo Bills", "BAL", "BUF", 0.55, 0.43, 0.42, 0.43, KO_1101,
                  qb_side="home", qb=["Josh Allen"])
    write_closing(ex, KO_1101 - timedelta(minutes=35), annotated([buf], KO_1101, market_only=False), fam="NFL")
    _world(tmp_path / "w11.db", extra=((15149, "Baltimore Ravens", "Buffalo Bills", KO_1101, 30, 13),))
    copy = _backup(tmp_path / "w11.db", tmp_path / "c11" / "nfl.db")
    fills = [_cockpit_entry(BUF_CELLS),
             _cockpit_entry(_csv_cells("KXNFLGAME-26NOV011300BALBUF-BUF", "yes", "Buffalo wins — Baltimore",
                                       "2026-11-01T17:21:00Z")),
             _cockpit_entry(_csv_cells("KXNFLGAME-26NOV01MIANE-NE", "no", "New England wins — Miami",
                                       "2026-11-01T17:22:00Z", exit_="0")),
             _cockpit_entry(_csv_cells("KXNFLGAME-26OCT25BALBUF-BUF", "yes", "Buffalo wins — Baltimore",
                                       "2026-10-25T17:20:00Z")),
             _cockpit_entry(EVENT_ONLY_CELLS),
             _cockpit_entry(_csv_cells("KXNFLSPREAD-26NOV01BALBUF-BUF3", "yes", "Buffalo wins by more than three?",
                                       "2026-11-01T17:24:00Z"))]
    led = tmp_path / "bd_ledger_v1_2026-11-03.json"
    led.write_text(json.dumps({"meta": {"policy_version": "v1.2"}, "calls": [], "fills": fills}, indent=1,
                              ensure_ascii=False))
    rc, out = _run(capsys, "--db", copy, "--exports", ex, "--ledger", led)
    assert rc == 0, out
    ln = _line(out, "Baltimore Ravens @ Buffalo Bills")
    assert "page: PLAY HOME (Buffalo Bills)" in ln and "QB-flagged half units" in ln, ln
    assert ln.endswith("what was done: fills: " + "; ".join(json.dumps(_held(f), ensure_ascii=False)
                                                            for f in fills[:2])), ln
    assert ("LEDGER: NFL game fills entries read 4 · fitting more than one row (ambiguous, given to none) 0 · PLAY rows "
            f"(scored + unscored) with fills on the game 1 of 1 · {WOULD} rows (scored + unscored) with fills on the "
            "game 0 of 0") in out
    led_lines = [x for x in out if x.startswith("LEDGER")]
    assert len(led_lines) == 1 and led_lines[0].startswith("LEDGER: "), led_lines
    j = json.loads(out[-1][len("QB-HOLD-RECEIPT "):])
    assert j["ambiguous_fills"] == 0 and "unmatched_nfl_fills" not in j and "not_game_market_fills" not in j
    assert j["what_was_done"] == {"play": {"fills": 1, "not_established": 0},
                                  "would_be": {"fills": 0, "not_established": 0}}
    body = "\n".join(x for x in out if not x.startswith(("RULING", "SOURCES", "WHAT WAS DONE FROM")))
    for fig in CSV_FIGURES + ("sub-s1", "\u241f", "category", "non-sport"):
        assert fig not in body, fig
    for key in IMPORT_KEYS[3:12] + ("id", "kind", "backed", "sideCode", "start"):    # ("teams": an unscored cause)
        assert f'"{key}"' not in body, key



# ---- the real Kalshi CSV's shape (#811, addendum 235 item 1): recognition of every NFL game fill ---------------------

# 235 item 1: "the header row is `type, quantity_fp, market_ticker, side, entry_price_dollars, exit_price_dollars,
# open_fees_dollars, close_fees_dollars, realized_pnl_without_fees_dollars, realized_pnl_with_fees_dollars,
# close_timestamp, open_timestamp, product, period_start, market_title`, plus the account-id column first" (its name
# here the one the Cockpit's own comment above mapHeaders records; its value synthetic and never printed)
RULING_HDR = ("subtrader_id", "type", "quantity_fp", "market_ticker", "side", "entry_price_dollars",
              "exit_price_dollars", "open_fees_dollars", "close_fees_dollars", "realized_pnl_without_fees_dollars",
              "realized_pnl_with_fees_dollars", "close_timestamp", "open_timestamp", "product", "period_start",
              "market_title")
# mapHeaders' predicates, the Cockpit's own text (tools/cockpit.html): the test pins each line, then ports it
MAP_HEADERS_JS = (
    'ticker:find(h=>has(h,"ticker")&&!has(h,"event")) ?? find(h=>has(h,"ticker")),',
    'side:find(h=>h==="side"||h.endsWith("_side")),',
    'qty:find(h=>h.startsWith("quantity")||h.startsWith("qty")||has(h,"contracts")||h==="count"),',
    'entry:find(h=>has(h,"entry")&&has(h,"price")),',
    'exit:find(h=>has(h,"exit")&&has(h,"price")),',
    'openFee:find(h=>has(h,"open")&&has(h,"fee")),',
    'closeFee:find(h=>has(h,"close")&&has(h,"fee")),',
    'openTs:find(h=>has(h,"open")&&(has(h,"time")||has(h,"ts")||has(h,"date"))&&!has(h,"fee")),',
    'closeTs:find(h=>has(h,"close")&&(has(h,"time")||has(h,"ts")||has(h,"date"))&&!has(h,"fee")),',
    'title:find(h=>has(h,"title")),')
# the ten event codes of 235 item 1 ("2 or 3 letters each"), each on a synthetic game: (date code, block, side code,
# away, home, the title's team, the start, naive UTC, and the ET offset the timestamps carry)
RULING_GAMES = (
    ("26OCT04", "GBTB", "GB", "Green Bay Packers", "Tampa Bay Buccaneers", "Green Bay", "2026-10-04T17:00:00", "-04:00"),
    ("26OCT05", "KCSEA", "KC", "Kansas City Chiefs", "Seattle Seahawks", "Kansas City", "2026-10-06T00:20:00", "-04:00"),
    ("26OCT11", "NYJNE", "NE", "New York Jets", "New England Patriots", "New England", "2026-10-11T17:00:00", "-04:00"),
    ("26OCT11", "BUFLV", "LV", "Buffalo Bills", "Las Vegas Raiders", "Las Vegas", "2026-10-11T20:05:00", "-04:00"),
    ("26OCT18", "WASSF", "WAS", "Washington Commanders", "San Francisco 49ers", "Washington", "2026-10-18T20:25:00",
     "-04:00"),
    ("26OCT18", "CARGB", "GB", "Carolina Panthers", "Green Bay Packers", "Green Bay", "2026-10-18T17:00:00", "-04:00"),
    ("26OCT25", "TBDAL", "TB", "Tampa Bay Buccaneers", "Dallas Cowboys", "Tampa Bay", "2026-10-25T17:00:00", "-04:00"),
    ("26OCT25", "DENARI", "ARI", "Denver Broncos", "Arizona Cardinals", "Arizona", "2026-10-25T20:05:00", "-04:00"),
    ("26NOV01", "BALBUF", "BUF", "Baltimore Ravens", "Buffalo Bills", "Buffalo", "2026-11-01T18:00:00", "-05:00"),
    ("26NOV01", "CLEPIT", "CLE", "Cleveland Browns", "Pittsburgh Steelers", "Cleveland", "2026-11-01T18:00:00", "-05:00"))
SPLITS = {"GBTB": "2+2", "KCSEA": "2+3", "TBDAL": "2+3", "NYJNE": "3+2", "BUFLV": "3+2", "WASSF": "3+2",
          "CARGB": "3+2", "DENARI": "3+3", "BALBUF": "3+3", "CLEPIT": "3+3"}
RULING_FIGURES = ("4417", "0.3863", "1.9131", "47.2209", "45.3078", "sub-r1")   # synthetic; never printed


def _ruling_day(code):
    from src.walters import ledger_fills as lf
    return f"20{code[:2]}-{lf.MONTHS[code[2:5]]:02d}-{code[5:7]}"


def _ruling_cells(g, side_code=None):
    """One CSV row of RULING_HDR in the ruling's forms (235 item 1): the MARKET ticker with its side suffix, the title
    "<Team> wins — <Team>" (an em dash), the timestamps with their offset, side lower-case yes; synthetic figures."""
    d, block, side, _away, _home, team, _ko, off = g
    day = _ruling_day(d)
    return ["sub-r1", "trade", "4417", f"KXNFLGAME-{d}{block}-{side_code or side}", "yes", "0.3863", "1", "1.9131", "0",
            "47.2209", "45.3078", f"{day}T15:31:07{off}", f"{day}T12:29:43{off}", "sports", day,
            f"{team} wins — {team}"]


def _map_headers(hdr):
    """mapHeaders (tools/cockpit.html), ported predicate by predicate (MAP_HEADERS_JS pins the Cockpit's text)."""
    n = [re.sub(r"[^a-z0-9]+", "_", str(h).lower()) for h in hdr]

    def find(pred):
        return next((i for i, h in enumerate(n) if pred(h)), None)

    def has(h, *ks):
        return all(k in h for k in ks)
    t = find(lambda h: has(h, "ticker") and not has(h, "event"))
    return {"ticker": t if t is not None else find(lambda h: has(h, "ticker")),
            "side": find(lambda h: h == "side" or h.endswith("_side")),
            "qty": find(lambda h: h.startswith(("quantity", "qty")) or has(h, "contracts") or h == "count"),
            "entry": find(lambda h: has(h, "entry") and has(h, "price")),
            "exit": find(lambda h: has(h, "exit") and has(h, "price")),
            "openFee": find(lambda h: has(h, "open") and has(h, "fee")),
            "closeFee": find(lambda h: has(h, "close") and has(h, "fee")),
            "openTs": find(lambda h: has(h, "open") and (has(h, "time") or has(h, "ts") or has(h, "date"))
                           and not has(h, "fee")),
            "closeTs": find(lambda h: has(h, "close") and (has(h, "time") or has(h, "ts") or has(h, "date"))
                            and not has(h, "fee")),
            "title": find(lambda h: has(h, "title"))}


def test_map_headers_reads_the_rulings_header_row_exactly():
    """235 item 1: "Code reads ... `mapHeaders` against exactly this header row (`market_ticker`, `market_title`,
    `open_timestamp`, `close_timestamp`, `quantity_fp`)". On the Cockpit's own predicates (pinned from its text): the
    ticker is market_ticker, qty quantity_fp, entry entry_price_dollars, the timestamps open_timestamp /
    close_timestamp (never a fee column: open_fees_dollars holds "open" too), the title market_title; the account-id
    column, product and period_start map to nothing. The fixture helper's header is this row, column for column."""
    html = COCKPIT.read_text()
    mh = html[html.index("function mapHeaders("):html.index("function num(")]
    for line in MAP_HEADERS_JS:
        assert line in mh, line
    assert 'const need=["ticker","qty","entry"].filter(k=>H[k]==null);' in html     # the import's required three
    assert RULING_HDR == KALSHI_HDR
    got = {k: RULING_HDR[v] for k, v in _map_headers(RULING_HDR).items()}
    assert got == {"ticker": "market_ticker", "side": "side", "qty": "quantity_fp", "entry": "entry_price_dollars",
                   "exit": "exit_price_dollars", "openFee": "open_fees_dollars", "closeFee": "close_fees_dollars",
                   "openTs": "open_timestamp", "closeTs": "close_timestamp", "title": "market_title"}
    assert not {"subtrader_id", "type", "product", "period_start"} & set(got.values())


def test_every_kalshi_nfl_game_ticker_is_recognised_whatever_its_codes_lengths():
    """235 item 1: "any parser that assumes two 3-letter codes drops roughly a third of the NFL fills". Neither the
    Cockpit's parseTicker nor its Python port assumes a length (the teams block is one [A-Z0-9]+ group): all ten
    event codes of the ruling, 2+2, 2+3, 3+2 and 3+3, parse as NFL game markets, the side resolved by the ticker's
    suffix (the block's prefix is AWAY, its suffix HOME), the date the ticker's own. The title in the ruling's form
    names one team, so the title's two teams are that team twice and the backed name stays unresolved (the role is
    the ticker's); positions() counts all ten as NFL game entries."""
    html = COCKPIT.read_text()
    assert r"/^KX([A-Z]+?)GAME-(\d{2})([A-Z]{3})(\d{2})(\d{4})?([A-Z0-9]+)-([A-Z0-9]+)$/" in html
    entries = []
    for g in RULING_GAMES:
        d, block, side, away, home, team, _ko, _off = g
        f = _cockpit_entry(_ruling_cells(g))
        a_len = len(side) if block.startswith(side) else len(block) - len(side)
        assert f"{a_len}+{len(block) - a_len}" == SPLITS[block], block
        assert (f["kind"], f["family"], f["teams"], f["sideCode"], f["date"], f["start"]) == (
            "sport", "NFL", block, side, _ruling_day(d), None), block
        assert f["backed_role"] == ("AWAY" if block.startswith(side) else "HOME"), block
        assert f["resolved_via"] == "ticker" and f["resolve_note"] is None and f["backed"] is None, block
        assert f["teams_title"] == [team, team] and f["opened"].endswith(_off), block
        entries.append(f)
    assert sorted(set(SPLITS.values())) == ["2+2", "2+3", "3+2", "3+3"]
    pos = script.positions({"calls": [], "fills": entries}, [])
    assert pos["nfl_fills"] == 10 and pos["by_row"] == {} and len(pos["unmatched"]) == 10


def _ruling_rows(events):
    return [{"key": 9000 + i, "home": g[4], "away": g[3], "kickoff_iso": g[6],
             "events": {f"KXNFLGAME-{g[0]}{g[1]}"} if events else set()} for i, g in enumerate(RULING_GAMES)]


def test_every_ruling_shaped_fill_matches_its_own_row_by_the_game_matcher_and_by_event():
    """Each of the ten entries, in the export's shape on the ruling's CSV forms, matches its own row and no other: by
    the Cockpit's game matcher on the row's full names (no event on the row) and by event ticker; the away or the home
    side alike. A reversed game (the same two teams, home and away swapped) fits no split. Nothing is ambiguous."""
    for side_of in ("given", "other"):
        entries = []
        for g in RULING_GAMES:
            block, side = g[1], g[2]
            other = block[len(side):] if block.startswith(side) else block[:-len(side)]
            entries.append(_cockpit_entry(_ruling_cells(g, side if side_of == "given" else other)))
        for events in (False, True):
            pos = script.positions({"calls": [], "fills": entries}, _ruling_rows(events))
            assert pos["nfl_fills"] == 10 and pos["ambiguous"] == 0 and pos["unmatched"] == [], (side_of, events)
            assert pos["by_row"] == {9000 + i: [_held(f)] for i, f in enumerate(entries)}, (side_of, events)
        flipped = [{**r, "home": r["away"], "away": r["home"]} for r in _ruling_rows(False)]
        pos = script.positions({"calls": [], "fills": entries}, flipped)
        assert pos["by_row"] == {} and len(pos["unmatched"]) == 10, side_of


def test_the_teams_block_split_is_settled_by_the_rows_names_never_by_length(monkeypatch):
    """The block's split is never fixed by length (235 item 1's 2-or-3 letters): the game matcher (ledger_fills.
    _codes_fit, the Cockpit's codesFit) tries every split with two letters or more a side, shortest away code first, and
    takes the game at the first split where BOTH codes fit the row's own names. Pinned on the matcher itself: a spy on
    its code_fits records the splits it tried, and the split it returned True on is the last one tried. GBTB has one
    split only (2+2; 3+1 and 1+3 are never tried); KCSEA is KC+SEA at the first try; NYJNE is NYJ+NE after NY+JNE is
    rejected; DENARI is DEN+ARI after DE+NARI is rejected; CARGB is CAR+GB after CA+RGB is rejected; TBDAL is TB+DAL.
    A reversed game rejects every split it tries, and the splits tried are exactly the 2-or-more-a-side ones. The side's
    role is the ticker's suffix, exact (GBTB-GB AWAY, GBTB-TB HOME), so a four-letter block of two two-letter codes is
    never ambiguous; a suffix that is both the block's prefix and its suffix is never guessed (no role)."""
    from src.walters import ledger_fills as lf
    real = lf.code_fits
    tried = []

    def spy(code, name):
        tried.append(code)
        return real(code, name)
    monkeypatch.setattr(lf, "code_fits", spy)

    def run(T, away, home):
        tried.clear()
        ok = lf._codes_fit(T, {"away": away, "home": home})
        pairs = [(tried[i], tried[i + 1]) for i in range(0, len(tried), 2)]
        assert all(a + h == T for a, h in pairs), (T, pairs)
        return ok, pairs

    expect = {   # block: (away, home, the splits the matcher tries in order, the last being the one it takes)
        "GBTB": ("Green Bay Packers", "Tampa Bay Buccaneers", [("GB", "TB")]),
        "KCSEA": ("Kansas City Chiefs", "Seattle Seahawks", [("KC", "SEA")]),
        "NYJNE": ("New York Jets", "New England Patriots", [("NY", "JNE"), ("NYJ", "NE")]),
        "DENARI": ("Denver Broncos", "Arizona Cardinals", [("DE", "NARI"), ("DEN", "ARI")]),
        "CARGB": ("Carolina Panthers", "Green Bay Packers", [("CA", "RGB"), ("CAR", "GB")]),
        "TBDAL": ("Tampa Bay Buccaneers", "Dallas Cowboys", [("TB", "DAL")]),
    }
    for T, (away, home, pairs) in expect.items():
        assert run(T, away, home) == (True, pairs), T
    every = {4: [(2, 2)], 5: [(2, 3), (3, 2)], 6: [(2, 4), (3, 3), (4, 2)]}
    for g in RULING_GAMES:                       # all ten, on the row's names: taken; the game reversed: every split out
        T, away, home = g[1], g[3], g[4]
        ok, pairs = run(T, away, home)
        assert ok and pairs[-1] == (T[:len(T) - len(pairs[-1][1])], pairs[-1][1]), T
        assert SPLITS[T] == f"{len(pairs[-1][0])}+{len(pairs[-1][1])}", (T, pairs[-1])
        ok, pairs = run(T, home, away)
        assert not ok and [(len(a), len(h)) for a, h in pairs] == every[len(T)], (T, pairs)
    monkeypatch.undo()
    for block, side, role in (("GBTB", "GB", "AWAY"), ("GBTB", "TB", "HOME"), ("KCSEA", "KC", "AWAY"),
                              ("KCSEA", "SEA", "HOME"), ("CARGB", "GB", "HOME"), ("TBDAL", "TB", "AWAY")):
        assert lf.ticker_role({"teams": block, "sideCode": side})["role"] == role, (block, side)
    assert lf.ticker_role({"teams": "GBGB", "sideCode": "GB"})["role"] is None        # both: never guessed


def test_a_code_that_fits_no_name_matches_by_event_only_under_the_one_team_title():
    """The export's title names one team, so the strict two-team title fallback (game_fits' docstring) never fits it:
    a code that prefixes no team name matches by the row's event ticker only. The synthetic code here (QQX) is not a
    provider code; Kalshi's real code per team is not enumerated in this repo, so whether any NFL team carries such a
    code is NOT established (law 1). A code that does prefix its name (a JAC-style code for "Jacksonville") fits by
    code with no event on the row."""
    from src.walters import ledger_fills as lf
    away, home = "Jacksonville Jaguars", "Tennessee Titans"
    assert not lf._codes_fit("QQXTEN", {"away": away, "home": home})
    assert lf._codes_fit("JACTEN", {"away": away, "home": home})
    g = ("26NOV01", "QQXTEN", "QQX", away, home, "Jacksonville", "2026-11-01T18:00:00", "-05:00")
    f = _cockpit_entry(_ruling_cells(g))
    assert f["teams_title"] == ["Jacksonville", "Jacksonville"] and not lf._title_fits_strict(f["teams_title"],
                                                                                            {"away": away, "home": home})
    row = {"key": 15150, "home": home, "away": away, "kickoff_iso": g[6], "events": set()}
    assert script.positions({"calls": [], "fills": [f]}, [row])["by_row"] == {}
    row["events"] = {"KXNFLGAME-26NOV01QQXTEN"}
    assert script.positions({"calls": [], "fills": [f]}, [row])["by_row"] == {15150: [_held(f)]}
    g2 = ("26NOV01", "JACTEN", "JAC", away, home, "Jacksonville", "2026-11-01T18:00:00", "-05:00")
    f2 = _cockpit_entry(_ruling_cells(g2))
    row2 = {"key": 15150, "home": home, "away": away, "kickoff_iso": g2[6], "events": set()}
    assert script.positions({"calls": [], "fills": [f2]}, [row2])["by_row"] == {15150: [_held(f2)]}


def test_the_one_team_title_never_matches_on_its_own():
    """The ruling's title ("Buffalo wins — Buffalo") names one team: the title fallback (two title teams on two
    different sides) can never fit, so the match rests on the ticker's codes or the event. Names the codes cannot fit
    and no event on the row: no row; the event on the row: matched."""
    g = RULING_GAMES[8]
    f = _cockpit_entry(_ruling_cells(g))
    assert f["title"] == "Buffalo wins — Buffalo" and f["teams_title"] == ["Buffalo", "Buffalo"]
    row = {"key": 15149, "home": "Synthetic Home", "away": "Synthetic Away", "kickoff_iso": g[6], "events": set()}
    assert script.positions({"calls": [], "fills": [f]}, [row])["by_row"] == {}
    row["events"] = {"KXNFLGAME-26NOV01BALBUF"}
    assert script.positions({"calls": [], "fills": [f]}, [row])["by_row"] == {15149: [_held(f)]}


# ---- 235 item 2(b): a Record-fill on the call, a hand entry; 235 item 2(c): --unmatched -----------------------------

HAND = "recorded on the call, a hand entry"
FILL_PRICE = "0.5317"                                           # synthetic Record-fill price: never printed


def _hand_call(**kw):
    c = {"id": "h1", "sport": "NFL", "game": "Baltimore Ravens @ Buffalo Bills", "home": "Buffalo Bills",
         "away": "Baltimore Ravens", "match_id": 15149, "kickoff": "2026-11-01T18:00:00Z", "pick": "HOME",
         "call_type": "straight", "engine": "model_edge", "status": "open", "units": 0.5,
         "order_type": "limit", "fill_price": float(FILL_PRICE), "fill_recorded_at": "2026-11-01T17:41:09.000Z"}
    c.update(kw)
    return {k: v for k, v in c.items() if v is not None}


def test_hand_entries_match_a_call_by_its_own_match_id_teams_and_kickoff():
    """235 item 2(b): a call is the row's game by its own identity (addendum 109 item 2: match id and recorded kickoff),
    its teams the row's: the field NAMES present come back, never a value. Another match id, other teams, a kickoff
    beyond the Desk's clock drift, no match id, no kickoff, another sport, or no Record-fill field: no row's. A call
    with only some of the fields names only those."""
    rows = _rows_1101()
    assert script.hand_entries({"calls": [_hand_call()]}, rows) == {
        15149: [["order_type", "fill_price", "fill_recorded_at"]]}
    assert script.hand_entries({"calls": [_hand_call(order_type=None, fill_recorded_at=None)]}, rows) == {
        15149: [["fill_price"]]}
    assert script.hand_entries({"calls": [_hand_call(kickoff="2026-11-01T18:59:00")]}, rows) == {
        15149: [["order_type", "fill_price", "fill_recorded_at"]]}                 # within the hour: the same start
    for bad in (dict(match_id=15150), dict(match_id=None), dict(match_id="15149"), dict(match_id=True),
                dict(kickoff=None), dict(kickoff="2026-11-01T19:01:00Z"), dict(home="Miami Dolphins"),
                dict(sport="MLB"), dict(order_type=None, fill_price=None, fill_recorded_at=None)):
        assert script.hand_entries({"calls": [_hand_call(**bad)]}, rows) == {}, bad
    assert script.hand_text(None) == "" and script.hand_text([]) == ""
    assert script.hand_text([["order_type", "fill_price"]]) == f" · {HAND}: order_type, fill_price"


def _export_world(tmp_path, fills, calls):
    ex = tmp_path / "ex35"
    buf = nfl_row(15149, "Baltimore Ravens", "Buffalo Bills", "BAL", "BUF", 0.55, 0.43, 0.42, 0.43, KO_1101,
                  qb_side="home", qb=["Josh Allen"])
    write_closing(ex, KO_1101 - timedelta(minutes=35), annotated([buf], KO_1101, market_only=False), fam="NFL")
    _world(tmp_path / "w35.db", extra=((15149, "Baltimore Ravens", "Buffalo Bills", KO_1101, 30, 13),))
    copy = _backup(tmp_path / "w35.db", tmp_path / "c35" / "nfl.db")
    led = tmp_path / "bd_ledger_v1_2026-11-03.json"
    led.write_text(json.dumps({"meta": {"policy_version": "v1.2"}, "calls": calls, "fills": fills}, indent=1,
                              ensure_ascii=False))
    return ex, copy, led


def test_a_record_fill_prints_under_its_own_label_never_merged_into_fills(capsys, tmp_path):
    """235 item 2(b): "a Record-fill written onto a call is the operator's hand entry and, if the export carries it,
    prints under its own label ("recorded on the call, a hand entry"), never merged into fills and never relabelled".
    With no fills on the game, "what was done" stays "not established" and the hand entry follows under its own label;
    with a fill, the fills print as before and the hand entry after them. The LEDGER line and the JSON's
    what_was_done count fills only. No price, order type or time of the Record-fill is printed."""
    for fills in ([], [_cockpit_entry(_ruling_cells(RULING_GAMES[8]))]):
        sub = tmp_path / f"f{len(fills)}"
        sub.mkdir()
        ex, copy, led = _export_world(sub, fills, [_hand_call()])
        rc, out = _run(capsys, "--db", copy, "--exports", ex, "--ledger", led)
        assert rc == 0, out
        ln = _line(out, "Baltimore Ravens @ Buffalo Bills")
        done = ("fills: " + json.dumps(_held(fills[0]), ensure_ascii=False)) if fills else "not established"
        assert ln.endswith(f"what was done: {done} · {HAND}: order_type, fill_price, fill_recorded_at"), ln
        j = json.loads(out[-1][len("QB-HOLD-RECEIPT "):])
        assert j["what_was_done"]["play"] == {"fills": len(fills), "not_established": 1 - len(fills)}
        assert (f"PLAY rows (scored + unscored) with fills on the game {len(fills)} of 1") in "\n".join(out)
        body = "\n".join(x for x in out if not x.startswith(("RULING", "SOURCES", "WHAT WAS DONE FROM", "KEYS")))
        for fig in (FILL_PRICE, "0.53", "17:41", '"h1"') + RULING_FIGURES:
            assert fig not in body, fig
        tail = ln.split(" · what was done: ", 1)[1]                    # the order type's value is never printed
        assert "limit" not in tail and "market" not in tail, tail
    # no Record-fill on the call: nothing of it prints
    sub = tmp_path / "none"
    sub.mkdir()
    ex, copy, led = _export_world(sub, [], [_hand_call(order_type=None, fill_price=None, fill_recorded_at=None)])
    rc, out = _run(capsys, "--db", copy, "--exports", ex, "--ledger", led)
    assert rc == 0 and HAND not in "\n".join(x for x in out if not x.startswith("KEYS"))


def test_unmatched_prints_each_unmatched_nfl_fill_event_and_date_only_behind_the_flag(capsys, tmp_path):
    """235 item 2(c): "a diagnostic line naming the event ticker and date of each NFL fill that matched no row — behind
    a flag (`--unmatched`), printed to the console only". The flag adds a head line (not for posting) and one line per
    unmatched NFL game entry: its event ticker and the ticker's date, nothing else (no side, title, figure or id); the
    entry on the row's game and a non-NFL entry print none. Without the flag nothing of it prints and every other line
    and the JSON are the same."""
    fills = [_cockpit_entry(_ruling_cells(g)) for g in RULING_GAMES]         # one on match 15149 (BALBUF), nine not
    fills.append(_cockpit_entry(_csv_cells("KXMLBGAME-26OCT18NYYBOS-BOS", "yes", "Boston wins — Boston",
                                           "2026-10-18T12:29:43-04:00")))
    ex, copy, led = _export_world(tmp_path, fills, [])
    rc0, out0 = _run(capsys, "--db", copy, "--exports", ex, "--ledger", led)
    rc1, out1 = _run(capsys, "--db", copy, "--exports", ex, "--ledger", led, "--unmatched")
    assert rc0 == rc1 == 0, out1
    assert not [x for x in out0 if "UNMATCHED" in x or "unmatched NFL" in x]
    extra = [x for x in out1 if x not in out0]
    assert out0 == [x for x in out1 if x not in extra]                          # nothing else changes, the JSON included
    assert extra[0] == (f"{script.UNMATCHED_HEAD}: NFL game fills entries read that matched no row 9")
    assert "NOT FOR POSTING" in extra[0]
    want = [f"  unmatched NFL game fill (not for posting): KXNFLGAME-{g[0]}{g[1]} · {_ruling_day(g[0])}"
            for g in RULING_GAMES if g[1] != "BALBUF"]
    assert extra[1:] == want
    for x in extra:
        for fig in RULING_FIGURES + ("yes", "wins", "-05:00", "-04:00", "KXMLB"):
            assert fig not in x, (fig, x)
    assert "LEDGER: NFL game fills entries read 10 " in "\n".join(out1)
    # the flag without --ledger: one line saying so, nothing else
    rc, out = _run(capsys, "--db", copy, "--exports", ex, "--unmatched")
    assert rc == 0 and [x for x in out if "UNMATCHED" in x] == [f"{script.UNMATCHED_HEAD}: not read (no --ledger)"]


def test_a_record_fill_on_an_unscored_row_prints_at_the_end_of_its_line(capsys, tmp_path):
    """231 item 2(c) keeps "what was done" on every row: an unscored row (here the copy lacks match 15149, "no result
    in this copy") carries the hand entry after it too, matched on the closing row's own teams and recorded start."""
    ex = tmp_path / "exu"
    buf = nfl_row(15149, "Baltimore Ravens", "Buffalo Bills", "BAL", "BUF", 0.55, 0.43, 0.42, 0.43, KO_1101,
                  qb_side="home", qb=["Josh Allen"])
    write_closing(ex, KO_1101 - timedelta(minutes=35), annotated([buf], KO_1101, market_only=False), fam="NFL")
    _world(tmp_path / "wu.db")
    copy = _backup(tmp_path / "wu.db", tmp_path / "cu" / "nfl.db")
    led = tmp_path / "bd_ledger_v1_2026-11-03.json"
    led.write_text(json.dumps({"calls": [_hand_call()], "fills": []}))
    rc, out = _run(capsys, "--db", copy, "--exports", ex, "--ledger", led)
    assert rc == 0, out
    hit = [x for x in out if x.startswith("  no result in this copy (unscored, counted): match 15149 ")]
    assert len(hit) == 1 and hit[0].endswith(
        f"what was done: not established · {HAND}: order_type, fill_price, fill_recorded_at"), hit
