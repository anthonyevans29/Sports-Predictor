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
thirty, labelled, outside the W-L-P (225 item 3); the refusals.
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


def _world(path: Path, moved: dict | None = None):
    from src.db.schema import Base, Competition, Match, MatchStatus, Odds, Sport, Team
    eng = create_engine(f"sqlite:///{path}", future=True)
    Base.metadata.create_all(eng)
    games = ((101, "Cleveland Browns", "New York Jets", KO_1011, 17, 12, MatchStatus.FINISHED, (1.65, 2.3)),
             (102, "Baltimore Ravens", "Atlanta Falcons", KO_1011, 23, 30, MatchStatus.FINISHED, (1.55, 2.5)),
             (103, "Detroit Lions", "Chicago Bears", KO_1011, 20, 24, MatchStatus.FINISHED, (1.65, 2.3)),
             (104, "Kansas City Chiefs", "Las Vegas Raiders", KO_1018, 21, 17, MatchStatus.FINISHED, (2.2, 1.7)),
             (105, "Seattle Seahawks", "Los Angeles Rams", KO_1109, None, None, MatchStatus.SCHEDULED, None))
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
    assert ("LEDGER: NFL game fills entries read 2 · fitting more than one row (ambiguous, given to none) 0 · PLAY scored "
            f"rows with fills on the game 1 of 3 · {WOULD} scored rows with fills on the game 1 of 1 (an unscored row "
            "is not matched to fills)") in out
    count = [ln for ln in out if ln.startswith("COUNT toward thirty")]
    assert count == [f"COUNT toward thirty (#446; addendum 44 item 9, 209 item 3; would-be rows counted too, labelled, "
                     f"217 item 4; unscored rows counted too, labelled, outside the W-L-P, 225 item 3): PLAY 4 + {WOULD} "
                     "2 = 6 of 30 — not read before thirty rows or the season's end (no verdict is computed here) · "
                     "PLAY W-L-P 2-1-0, void 0, open 0, unscored 1 (no result in this copy 1 · teams differ 0 · "
                     f"re-dated void 0) · {WOULD} W-L-P 0-0-0, void 0, open 1, unscored 1 (no result in this copy 1 · "
                     "teams differ 0 · re-dated void 0)"]
    assert out[-1].startswith("QB-HOLD-RECEIPT ")
    j = json.loads(out[-1][len("QB-HOLD-RECEIPT "):])
    assert (j["play_rows"], j["would_be_rows"], j["toward_thirty"], j["thirty_reached"]) == (3, 1, 6, False)
    assert j["counted"] == {"play": 4, "would_be": 2}
    assert j["what_was_done"] == {"play": {"fills": 1, "not_established": 2},
                                  "would_be": {"fills": 1, "not_established": 0}}


def test_a_would_be_row_with_no_ledger_entry_stays_blank(world, capsys, tmp_path):
    """223 item 5(a): "a would-be row with no ledger position stays blank" — the blank a PLAY row has (46 item 4)."""
    led = tmp_path / "led-blank.json"
    led.write_text(json.dumps({**LEDGER, "fills": [f for f in LEDGER["fills"] if f["id"] != "f-sea"]}))
    rc, out = _run(capsys, "--db", world["copy"], "--exports", world["ex"], "--ledger", led)
    assert rc == 0
    assert _line(out, "Seattle Seahawks @ Los Angeles Rams").endswith("what was done: not established")
    assert _line(out, "Cleveland Browns @ New York Jets").endswith("what was done: not established")
    j = json.loads(out[-1][len("QB-HOLD-RECEIPT "):])
    assert j["what_was_done"]["would_be"] == {"fills": 0, "not_established": 1}


def test_the_two_sources_and_no_result_in_this_copy(world, capsys):
    """223 item 5(b): the results from the DB copy stay; the header names the copy and the closing-file directory as
    the two sources; a row whose game the copy lacks is labelled "no result in this copy", never scored, and (225 item
    3) counted toward thirty as a labelled, unscored row."""
    rc, out = _run(capsys, "--db", world["copy"], "--exports", world["ex"], "--ledger", world["ledger"])
    assert rc == 0
    src = [ln for ln in out if ln.startswith("SOURCES")]
    assert len(src) == 1 and src[0].startswith(f"SOURCES (the two, 223 item 5(b)): the copy --db {world['copy']} (a "
                                               ".backup copy, opened mode=ro&immutable=1; the results, as "
                                               "results-tally reads them: exec_cohorts.result_of) · the closing-file "
                                               f"directory {world['ex']} (closing_*.json"), src
    assert f"WHAT WAS DONE FROM: ledger {world['ledger']} (bd_ledger_v1: calls 1, fills 3)" in out
    assert (f"UNSCORED (counted toward thirty, labelled, never scored, outside the W-L-P, 225 item 3; per kind, never "
            f"pooled): PLAY — no result in this copy 1 · teams differ 0 · re-dated void 0 (re-dated 0 · placeholder "
            f"kickoff 0); {WOULD} — no result in this copy 1 · teams differ 0 · re-dated void 0 (re-dated 0 · "
            "placeholder kickoff 0)") in out
    assert "  no result in this copy (unscored, counted): match 999 Miami Dolphins @ Buffalo Bills (PLAY)" in out
    assert (f"  no result in this copy (unscored, counted): match 998 New York Giants @ Philadelphia Eagles ({WOULD})"
            in out)
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
    fills) + 1 unscored (225 item 3: counted): a pooled figure would read 6 counted, 4 scored, 2 with fills, 2 with no
    result in this copy."""
    rc, out = _run(capsys, "--db", world["copy"], "--exports", world["ex"], "--ledger", world["ledger"])
    assert rc == 0
    count = [ln for ln in out if ln.startswith("COUNT toward thirty")]
    assert len(count) == 1 and f"PLAY 4 + {WOULD} 2 = 6 of 30" in count[0]
    for ln in out:
        if ln in count or ln.startswith(("RULING", "KEYS", "SOURCES", "WHAT WAS DONE FROM", "QB-HOLD-RECEIPT")):
            continue
        assert not re.search(r"\bof [46]\b", ln), ln                   # rows, both kinds: only the count's
        assert not re.search(r"(fills on the game|no result in this copy) 2\b", ln), ln
        assert not re.search(r"\b2 of\b", ln), ln
    j = json.loads(out[-1][len("QB-HOLD-RECEIPT "):])
    # every row count lives under a kind's key; the whitelisted top-level figures are not row tallies of both kinds
    whole = {("closing_files",), ("unreadable",), ("nfl_games",), ("read_at",), ("ambiguous_fills",),
             ("toward_thirty",), ("play_rows",), ("would_be_rows",)}
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
    assert ("LEDGER: NFL game fills entries read 1 · fitting more than one row (ambiguous, given to none) 1 · PLAY scored "
            f"rows with fills on the game 0 of 2 · {WOULD} scored rows with fills on the game 0 of 0 (an unscored row "
            "is not matched to fills)") in out


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
            "2026-10-11 17:00Z → 2026-10-12 17:00Z") in out
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
            "placeholder kickoff") in out
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
    labelled = {
        "  no result in this copy (unscored, counted): match 999 Miami Dolphins @ Buffalo Bills (PLAY)",
        "  teams differ (unscored, counted): match 103 Green Bay Packers @ Minnesota Vikings (PLAY; this database's "
        "match 103 is Detroit Lions @ Chicago Bears)",
        "  re-dated void (unscored, counted): match 102 Baltimore Ravens @ Atlanta Falcons (PLAY): void: re-dated "
        "2026-10-11 17:00Z → 2026-10-12 17:00Z",
        f"  no result in this copy (unscored, counted): match 998 New York Giants @ Philadelphia Eagles ({WOULD})",
        f"  teams differ (unscored, counted): match 104 Denver Broncos @ Houston Texans ({WOULD}; this database's "
        "match 104 is Kansas City Chiefs @ Las Vegas Raiders)"}
    assert labelled <= set(out), sorted(labelled - set(out))
    assert len([ln for ln in out if "(unscored, counted): " in ln]) == 5
    rows = [ln for ln in out if ln.startswith("- ")]                       # the scored rows only: 101 and 105
    assert [re.search(r"\[match (\d+)\]", ln).group(1) for ln in rows] == ["101", "105"], rows
    assert (f"UNSCORED (counted toward thirty, labelled, never scored, outside the W-L-P, 225 item 3; per kind, never "
            f"pooled): PLAY — no result in this copy 1 · teams differ 1 · re-dated void 1 (re-dated 1 · placeholder "
            f"kickoff 0); {WOULD} — no result in this copy 1 · teams differ 1 · re-dated void 0 (re-dated 0 · "
            "placeholder kickoff 0)") in out
    count = [ln for ln in out if ln.startswith("COUNT toward thirty")]
    assert count == [f"COUNT toward thirty (#446; addendum 44 item 9, 209 item 3; would-be rows counted too, labelled, "
                     f"217 item 4; unscored rows counted too, labelled, outside the W-L-P, 225 item 3): PLAY 4 + {WOULD} "
                     "3 = 7 of 30 — not read before thirty rows or the season's end (no verdict is computed here) · "
                     "PLAY W-L-P 0-1-0, void 0, open 0, unscored 3 (no result in this copy 1 · teams differ 1 · "
                     f"re-dated void 1) · {WOULD} W-L-P 0-0-0, void 0, open 1, unscored 2 (no result in this copy 1 · "
                     "teams differ 1 · re-dated void 0)"], count
    j = json.loads(out[-1][len("QB-HOLD-RECEIPT "):])
    assert j["unscored"] == {"play": {"no_result": 1, "teams": 1, "void": 1},
                             "would_be": {"no_result": 1, "teams": 1, "void": 0}}
    assert (j["play_rows"], j["would_be_rows"]) == (1, 1)                  # the scored rows, the W-L-P's
    assert j["play_record"] == {"win": 0, "loss": 1, "push": 0, "void": 0, "open": 0}
    assert j["would_be_record"] == {"win": 0, "loss": 0, "push": 0, "void": 0, "open": 1}
    assert (j["counted"], j["toward_thirty"], j["thirty_reached"]) == ({"play": 4, "would_be": 3}, 7, False)
    assert "PLAY 4 + " in count[0] and f"{WOULD} 3 = 7 of 30" in count[0]   # the printed count is the JSON's


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
    assert len(count) == 1 and (f"PLAY 30 + {WOULD} 0 = 30 of 30 — thirty reached — for the architect's read (no "
                                "verdict is computed here) · PLAY W-L-P 0-0-0, void 0, open 0, unscored 30 (no result "
                                "in this copy 30 · teams differ 0 · re-dated void 0)") in count[0], count
    assert len([ln for ln in out if ln.startswith("  no result in this copy (unscored, counted): match 9")]) == 30
    assert not [ln for ln in out if ln.startswith("- ")]
    j = json.loads(out[-1][len("QB-HOLD-RECEIPT "):])
    assert (j["toward_thirty"], j["thirty_reached"], j["play_rows"]) == (30, True, 0)


def test_the_count_line_says_thirty_reached_and_never_a_verdict():
    g = {"win": 0, "loss": 0, "push": 0, "void": 0, "open": 0}
    assert "= 29 of 30 — not read before thirty rows" in script.count_line(29, 0, g, g)
    line = script.count_line(25, 5, g, g)
    assert f"PLAY 25 + {WOULD} 5 = 30 of 30 — thirty reached — for the architect's read (no verdict is computed here)" \
        in line
    for w in ("PASS", "FAIL", "verdict:"):
        assert w not in line
    line = script.count_line(20, 10, g, g, {"no_result": 4, "teams": 1, "void": 1}, {"no_result": 2})
    assert f"PLAY 20 + {WOULD} 10 = 30 of 30 — thirty reached" in line
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


# ---- the review findings (Codex P2s): host/ never read, a figure in a printed field refused, every entry its own ----

def test_an_exports_directory_named_host_is_refused_even_through_a_symlink(world, capsys, tmp_path):
    """The SOURCES line says "host/ never read": a --exports that is (or resolves to) a host/ directory is refused,
    nothing read (its closing files carry the host's match ids); a normal exports directory is still read."""
    host = tmp_path / "mirror" / "host"
    write_closing(host, KO_1011 - timedelta(minutes=35),
                  annotated([cle_nyj(), bal_atl()], KO_1011, market_only=False), fam="NFL")
    rc, out = _run(capsys, "--db", world["copy"], "--exports", host, "--ledger", world["ledger"])
    assert rc == 2 and len(out) == 1, out
    assert out[0].startswith(f"REFUSED: --exports {host}: names or resolves to a host/ directory") and \
        "host/ is never read, its files carry the host's match ids; nothing read" == out[0].split("); ", 1)[1], out
    link = tmp_path / "looks-fine"
    link.symlink_to(host, target_is_directory=True)
    rc, out = _run(capsys, "--db", world["copy"], "--exports", link)
    assert rc == 2 and len(out) == 1 and out[0].startswith(f"REFUSED: --exports {link}: names or resolves to a "
                                                           f"host/ directory ({host.resolve()})"), out
    assert out[0].endswith("nothing read")
    # a link NAMED host to a directory of another name is refused by its own name (review finding)
    named = tmp_path / "links" / "host"
    named.parent.mkdir()
    named.symlink_to(world["ex"], target_is_directory=True)
    rc, out = _run(capsys, "--db", world["copy"], "--exports", named)
    assert rc == 2 and len(out) == 1 and out[0].startswith(f"REFUSED: --exports {named}: names or resolves to a "
                                                           f"host/ directory ({Path(world['ex']).resolve()})"), out
    # any case: a Mac's default volume opens exports/HOST as exports/host (review finding)
    for spelt in ("HOST", "Host"):
        upper = tmp_path / "cased" / spelt
        upper.mkdir(parents=True)
        rc, out = _run(capsys, "--db", world["copy"], "--exports", upper)
        assert rc == 2 and len(out) == 1 and out[0].endswith("nothing read") and \
            "names or resolves to a host/ directory" in out[0], out
    rc, out = _run(capsys, "--db", world["copy"], "--exports", world["ex"])
    assert rc == 0 and _line(out, "Cleveland Browns @ New York Jets")


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
