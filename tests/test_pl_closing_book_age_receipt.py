"""Addendum 446 item 2 (Refs #348): the PL closing-page book age receipt, read-only.

A throwaway SQLite copy (never data/) built through the ORM, the unmapped odds_snapshots.source_updated_at added by
ALTER TABLE as migrate_odds_source_updated_at.py would (tests/test_book_stamp_age_receipt.py's pattern; `stamp=False`
leaves it out), and closing pages as a closing run writes them (tests/test_pl_injury_classification_receipt.py's
pattern). Covers M3, M4, a moved price, a page that matches an earlier session, no session matching, the column
absent, the "at least" lower bound, an incomplete session (and one carrying another price ending the run), a partly
stamped session, the season/competition filter, a re-paged start, a copy, pages with no run start, a match found by
teams and kickoff (and a page id naming another game or kickoff, an ambiguous lookup), the line_move cross-check, the
buckets' edges, --from / --through, sessions after the export, exported_at with microseconds and a Z, the 198 fence set
(the app's configured database, a write refused), latest/ refused, exit codes and the copy's bytes unchanged."""
import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("pl_closing_book_age_receipt",
                                               ROOT / "scripts" / "pl_closing_book_age_receipt.py")
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)


def _dt(v):
    return datetime.fromisoformat(v)


D = "2026-11-21T"
T1030, T1100, T1155, T1205, T1305, T1425 = (D + "10:30:12", D + "11:00:35.500000", D + "11:55:30",
                                            D + "12:05:20", D + "13:05:20", D + "14:25:10.250000")
EXP_1500 = D + "14:27:03.123456Z"          # utc_now_naive().isoformat() + "Z" (export.py:85)
EXP_1230 = D + "11:57:01.500000Z"
X0 = (0.401234, 0.289876, 0.30889)
X1 = (0.452311, 0.271502, 0.276187)
X1B = (0.4523112, 0.2715018, 0.276187)     # identical to X1 at 4 places, not as stored (a move below the rounding)
X2 = (0.500111, 0.250222, 0.249667)
SELS = ("HOME", "DRAW", "AWAY")

GAMES = {   # id: (home, away, kickoff, [(captured_at, triple, stamp, legs)])
    100: ("Chelsea", "Arsenal", D + "15:00:00",
          [(T1030, X1B, D + "10:20:00", SELS), (T1100, X1, D + "10:50:00", SELS), (T1205, X1, D + "10:50:00", SELS),
           (T1305, X1, D + "10:50:00", SELS), (T1425, X1, D + "10:50:00", SELS)]),                 # M3
    101: ("Liverpool", "Everton", D + "15:00:00",
          [(T1030, X0, D + "10:20:00", SELS), (T1100, X1, D + "10:50:00", SELS), (T1205, X1, D + "12:00:00", SELS),
           (T1425, X1, D + "14:20:00", SELS)]),                                                     # M4
    102: ("Tottenham", "Fulham", D + "15:00:00",
          [(T1100, X0, D + "10:50:00", SELS), (T1425, X1, D + "14:20:00", SELS),
           (D + "14:30:00", X2, D + "14:29:00", SELS), (D + "15:05:00", X2, D + "15:04:00", SELS)]),   # moved: fresh
    103: ("Leeds", "Burnley", D + "15:00:00",
          [(T1100, X0, D + "10:50:00", SELS), (T1205, X1, D + "12:00:00", SELS),
           (T1425, X2, D + "14:20:00", SELS)]),                                                     # earlier session
    104: ("Wolves", "Brentford", D + "15:00:00",
          [(T1100, X0, D + "10:50:00", SELS), (T1425, X1, D + "14:20:00", SELS)]),                 # no match
    105: ("Aston Villa", "Newcastle", D + "15:00:00",
          [(T1100, X1, None, SELS), (T1425, X1, None, SELS)]),                                     # unstamped
    106: ("Nottingham Forest", "Crystal Palace", D + "15:00:00",
          [(T1100, X0, D + "10:50:00", SELS), (T1205, X1, D + "12:00:00", SELS),
           (T1425, X2, D + "14:20:00", ("HOME", "AWAY"))]),                                         # incomplete
    107: ("Bournemouth", "Sunderland", D + "15:00:00", [(T1425, X1, D + "14:20:00", SELS)]),        # id disagrees
    108: ("Manchester United", "Brighton", D + "12:30:00",
          [(T1100, X1, D + "10:50:00", SELS), (T1155, X1, D + "10:50:00", SELS)]),
    109: ("West Ham", "Manchester City", D + "15:00:00", [(T1425, X1, D + "14:20:00", SELS)]),     # no fair on page
}


def build_db(path: Path, stamp: bool = True) -> None:
    from src.db.schema import Base, Competition, Match, MatchStatus, OddsSnapshot, Sport, Team
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    if stamp:
        with eng.begin() as c:
            c.execute(text("ALTER TABLE odds_snapshots ADD COLUMN source_updated_at DATETIME"))
    with Session(eng) as s:
        pl = Competition(sport=Sport.SOCCER, code="PL", name="Premier League", area="England", type="LEAGUE")
        s.add(pl)
        s.flush()
        teams = {}
        for mid, (h, a, ko, snaps) in GAMES.items():
            for n in (h, a):
                if n not in teams:
                    teams[n] = Team(sport=Sport.SOCCER, name=n)
                    s.add(teams[n])
            s.flush()
            s.add(Match(id=mid, sport=Sport.SOCCER, competition_id=pl.id, season="2026/27", utc_date=_dt(ko),
                        status=MatchStatus.SCHEDULED, home_team_id=teams[h].id, away_team_id=teams[a].id))
            s.flush()
            for at, tri, st, legs in snaps:
                for sel, v in zip(SELS, tri):
                    if sel not in legs:
                        continue
                    o = OddsSnapshot(match_id=mid, market="1X2", selection=sel, devig_prob=v, n_books=5,
                                     captured_at=_dt(at), source="api_football")
                    s.add(o)
                    s.flush()
                    if stamp and st is not None:
                        s.execute(text("UPDATE odds_snapshots SET source_updated_at = :t WHERE id = :i"),
                                  {"t": _dt(st).strftime("%Y-%m-%d %H:%M:%S.%f"), "i": o.id})
        # a kalshi leg and another source's book row on 100: never read
        s.add(OddsSnapshot(match_id=100, market="1X2", selection="HOME", devig_prob=0.9, captured_at=_dt(T1425),
                           source="kalshi"))
        s.add(OddsSnapshot(match_id=100, market="1X2", selection="HOME", devig_prob=0.9,
                           captured_at=_dt(D + "14:26:00"), source="other_book"))
        s.commit()
    eng.dispose()


def row(mid, tri=None, season="2026/27", comp="PL", lm=None, ko=None, teams=None):
    h, a, k, _ = GAMES.get(mid, ("Nobody", "Else", D + "15:00:00", []))
    if teams:
        h, a = teams
    sels = {} if tri is None else {s: {"fair_prob": round(v, 4), "best_price": 2.0,
                                       "best_bookmaker": "SecretBook"} for s, v in zip(SELS, tri)}
    return {"match_id": mid, "utc_date": ko or k, "competition": comp, "season": season, "home_team": h,
            "away_team": a, "market": {"selections": sels, "bookmaker_count": 5 if sels else 0},
            "line_move": lm}


def lm_book(to_at, to_st):
    return {"flag": None, "venues": {"book": {"from": 0.45, "to": 0.45, "move_pp": 0.0, "from_at": T1100,
                                              "to_at": to_at, "alarm": False, "from_source_updated_at": None,
                                              "to_source_updated_at": to_st}}}


def closing(folder: Path, start: str, exported: str, rows: list, fam="SOCCER", run_id=None, sha="841eba24c0ffee"):
    folder.mkdir(parents=True, exist_ok=True)
    st = _dt(start)
    doc = {"exported_at": exported, "git_sha": sha, "sport": "soccer", "competition_code": "PL",
           "count": len(rows), "predictions": rows,
           "closing": {"family": fam, "start": start + "Z", "run_id": run_id or f"run-{st:%m%d%H%M}",
                       "match_ids": [r["match_id"] for r in rows], "called_off": []}}
    p = folder / f"closing_{fam}_{st:%Y-%m-%dT%H%M}Z.json"
    p.write_text(json.dumps(doc))
    return p


def page_1500():
    return [row(100, X1, lm=lm_book(T1425, D + "10:50:00")),
            row(101, X1, lm=lm_book(T1425, D + "10:50:00")),        # the stamp differs: a cross-check DIFFER
            row(102, X1), row(103, X1), row(104, X2), row(105, X1),
            row(106, X1, lm=lm_book(T1305, D + "12:00:00")),         # to_at differs, the stamp agrees
            row(999, X1, teams=("Bournemouth", "Sunderland")),       # the page's id is not in the copy
            row(555),                                                # not in the copy at all
            row(109),                                                # no book fair on the page
            row(100, X1, comp="ELC"), row(100, X1, season="2025/26")]   # another competition / season


def write_exports(ex: Path):
    closing(ex, D + "15:00:00", EXP_1500, page_1500())
    closing(ex, D + "12:30:00", EXP_1230, [row(108, X1)])
    closing(ex, D + "15:00:00", EXP_1500, [row(100, X1)], fam="MLB")      # another family


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
    """The row's lines: from its '· match <mid> ' line to the next row or page."""
    i = next(k for k, ln in enumerate(out) if f" · match {mid} " in ln and ln.startswith("  "))
    j = i + 1
    while j < len(out) and out[j].startswith("    "):
        j += 1
    return "\n".join(out[i:j])


# ---- the measures ---------------------------------------------------------------------------------------------

def test_m3_stamp_age_from_the_stamp_last_change_from_1100(world):
    code, out = run(world)
    assert code == 0
    b = block(out, 100)
    assert "page fair H/D/A 0.4523/0.2715/0.2762" in b
    assert "priced session captured 2026-11-21 14:25:10Z · stamp 2026-11-21 10:50:00Z" in b
    assert "the latest complete session at or before the export" in b
    assert "capture age 2 min" in b                                   # 14:27:03.12 - 14:25:10.25
    assert "stamp age 217 min (a lower bound on the quote's age)" in b  # 14:27:03 - 10:50
    assert "last-change age 206 min (identical as stored across 4 session(s) from 2026-11-21 11:00:35Z)" in b
    # identical at 4 places further back (10:30, a move below the rounding), and that run reaches the first session
    assert "at 4 places at least 237 min (5 sessions from 2026-11-21 10:30:12Z" in b
    assert "HEADLINE 217 min (by the stamp)" in b
    assert "M3 (triple and stamp unchanged across 4 sessions)" in b
    assert "sessions after the export, before kickoff 0" in b
    assert "line_move book cross-check: agree" in b


def test_m4_identical_prices_with_a_moved_stamp(world):
    _code, out = run(world)
    b = block(out, 101)
    assert "stamp age 7 min" in b and "HEADLINE 7 min (by the stamp)" in b
    assert "last-change age 206 min (identical as stored across 3 session(s)" in b
    assert "M4 (triple unchanged across 3 sessions, the provider stamp moved 2 time(s))" in b
    assert "line_move book cross-check: differ (to_source_updated_at 2026-11-21T10:50:00 vs the priced " \
           "session's stamp 2026-11-21T14:20:00)" in b


def test_a_moved_price_is_fresh(world):
    _code, out = run(world)
    b = block(out, 102)
    assert "last-change age 2 min (identical as stored across 1 session(s) from 2026-11-21 14:25:10Z)" in b
    assert "fresh (the triple moved at this fetch)" in b and "at least" not in b
    assert "line_move book cross-check: absent" in b
    # 14:30 counts (after the 14:27 export, before the 15:00 kickoff); 15:05 is after kickoff and does not
    assert "sessions after the export, before kickoff 1 · " in b


def test_a_page_that_matches_an_earlier_session_is_labelled(world):
    _code, out = run(world)
    b = block(out, 103)
    assert "page matches an earlier session (captured 2026-11-21 12:05:20Z)" in b
    assert "capture age 142 min" in b and "stamp age 147 min" in b
    s = summary(out)
    assert s["earlier_session"] == 1


def test_no_stored_session_matches_the_page_counted_never_forced(world):
    _code, out = run(world)
    b = block(out, 104)
    assert "NOT PRICED: no stored session matches the page" in b
    assert summary(out)["status"]["no stored session matches the page"] == 1


def test_unstamped_rows_fall_back_to_the_last_change_at_least(world):
    _code, out = run(world)
    b = block(out, 105)
    assert "stamp unknown (the priced session's rows unstamped (NULL))" in b
    assert "last-change age at least 206 min" in b
    assert "HEADLINE at least 206 min (by the last change)" in b
    assert "stamp unknown in the run (M3 and M4 not told apart; 2 sessions, triple unchanged)" in b


def test_an_incomplete_session_is_skipped(world):
    _code, out = run(world)
    b = block(out, 106)
    assert "priced session captured 2026-11-21 12:05:20Z" in b
    assert "the latest complete session at or before the export" in b
    assert "incomplete sessions skipped 1" in b
    assert ("line_move book cross-check: differ (to_at 2026-11-21T13:05:20 vs the priced session "
            "2026-11-21T12:05:20)") in b


def test_a_match_found_by_teams_and_kickoff_when_the_id_disagrees(world):
    _code, out = run(world)
    b = block(out, 999)
    assert "on the copy: by both team names and the kickoff (the page's id 999 is not in the copy)" in b
    assert "first stored session (no earlier capture to compare)" in b and "last-change age at least 2 min" in b
    b = block(out, 555)
    assert "NOT PRICED: match not found in the copy" in b
    assert ("on the copy: match not found in the copy (the page's id 555 is not in the copy; no stored match with "
            "both team names") in b


def test_the_page_with_no_book_fair_is_counted(world):
    _code, out = run(world)
    assert "NOT PRICED: the page shows no book fair" in block(out, 109)


def test_season_competition_and_family_filters(world):
    code, out = run(world)
    s = summary(out)
    assert code == 0 and s["rows"] == 11 and s["pages"] == 2             # 10 rows at 15:00, 1 at 12:30
    assert s["files"]["other_rows"] == 2 and s["files"]["other_family"] == 1
    assert s["status"] == {"priced": 8, "no stored session matches the page": 1, "match not found in the copy": 1,
                           "the page shows no book fair (no complete H/D/A fair_prob)": 1}


def test_totals_distributions_and_slots(world):
    _code, out = run(world)
    s = summary(out)
    h = s["measures"]["headline"]
    assert h["n"] == 8 and sum(h["unknown"].values()) == 3
    assert h["by"] == {"stamp": 7, "last change (at least)": 1}
    st = s["measures"]["stamp"]
    assert st["n"] == 7 and st["unknown"]["the priced session's rows unstamped (NULL)"] == 1
    assert s["measures"]["last_change"]["at_least"] == 3
    # 101, 102, 107 (via 999) 7 min · 108 67 min · 103, 106 147 min · 100 217 min, 105 at least 206 min
    assert s["measures"]["headline"]["buckets"] == {"under 0 h (after the export)": 0, "0-1 h": 3, "1-2 h": 1,
                                                    "2-3 h": 2, "3-6 h": 2, "6-12 h": 0, "12 h or more": 0}
    assert s["mechanism"] == {"M3": 2, "M4": 1, "fresh": 3, "first stored session": 1, "stamp unknown": 1}
    assert s["line_move"] == {"agree": 1, "differ": 2, "absent": 5}
    assert set(s["by_slot"]) == {"Sat 15:00 UK", "Sat 12:30 UK"}
    assert s["by_slot"]["Sat 12:30 UK"]["rows"] == 1
    assert any(ln.startswith("BY KICKOFF SLOT") for ln in out)
    txt = "\n".join(out)
    assert "HEADLINE AGE (stamp where stored, else last change): n 8 · min " in txt
    assert "(of 11; unknowns in the denominator)" in txt


def test_the_1230_page_and_its_m3(world):
    _code, out = run(world)
    b = block(out, 108)
    assert "stamp age 67 min" in b and "M3 (triple and stamp unchanged across 2 sessions)" in b
    head = ("== page closing_SOCCER_2026-11-21T1230Z.json · run start 2026-11-21 12:30:00Z · exported_at "
            "2026-11-21T11:57:01.500000Z · git_sha 841eba24 · rows 1")
    assert any(ln.lstrip("\n").startswith(head) for ln in out)


def test_column_absent_stamp_unknown_headline_falls_back(tmp_path, world):
    db = tmp_path / "nostamp.db"
    build_db(db, stamp=False)
    _code, out = run(world, db=db)
    assert any("odds_snapshots.source_updated_at: ABSENT" in ln for ln in out)
    b = block(out, 100)
    assert "stamp unknown (odds_snapshots.source_updated_at absent on this copy)" in b
    assert "HEADLINE 206 min (by the last change)" in b
    s = summary(out)
    assert s["stamp_column"] is False and s["measures"]["stamp"]["n"] == 0
    assert s["measures"]["stamp"]["unknown"]["odds_snapshots.source_updated_at absent on this copy"] == 8


def test_exported_at_with_microseconds_and_z_parses(world):
    """export.py:85's form, parsed through redated.as_utc on 3.10 as on 3.12 (critic G12)."""
    assert rc.redated.as_utc(EXP_1500) == datetime(2026, 11, 21, 14, 27, 3, 123456)
    pop = rc.read_pages(world["ex"])
    assert {g["exported_at"] for g in pop["pages"]} == {datetime(2026, 11, 21, 14, 27, 3, 123456),
                                                        datetime(2026, 11, 21, 11, 57, 1, 500000)}


def test_two_pages_for_one_start_both_reported_and_a_copy_counted_once(world, tmp_path):
    tree = tmp_path / "host"
    closing(tree / "2026-11-21", D + "15:00:00", EXP_1500, [row(100, X1)], run_id="run-a")
    closing(tree / "2026-11-22", D + "15:00:00", D + "14:40:00.000001Z", [row(100, X1)], run_id="run-b")
    (tree / "2026-11-23").mkdir()
    (tree / "2026-11-23" / "closing_SOCCER_2026-11-21T1500Z.json").write_text(
        (tree / "2026-11-21" / "closing_SOCCER_2026-11-21T1500Z.json").read_text())
    code, out = run(world, ex=tree)
    assert code == 0
    heads = [ln.lstrip("\n") for ln in out if ln.lstrip("\n").startswith("== page ")]
    assert len(heads) == 3
    assert "RE-PAGED: page 1 of 2 for this run start" in heads[0] and heads[0].startswith("== page 2026-11-21/")
    assert "a COPY of 2026-11-21/closing_SOCCER_2026-11-21T1500Z.json" in heads[1]
    assert "RE-PAGED: page 2 of 2 for this run start" in heads[2] and heads[2].startswith("== page 2026-11-22/")
    s = summary(out)
    assert s["pages"] == 2 and s["rows"] == 2 and s["copies"] == 1 and s["repaged_starts"] == 1
    assert "capture age 15 min" in "\n".join(out)                    # the 14:40 page: 14:40 - 14:25:10


def test_the_bound_counts_pages_outside(world):
    code, out = run(world, "--from", "2026-11-21T13:00:00Z")
    s = summary(out)
    assert code == 0 and s["pages"] == 1 and s["files"]["outside"] == 1 and s["from"] == "2026-11-21T13:00:00Z"
    assert s["rows"] == 10


def test_through_is_exclusive_and_cuts_the_1500_page(world):
    code, out = run(world, "--through", "2026-11-21T13:00:00Z")
    s = summary(out)
    assert code == 0 and s["pages"] == 1 and s["rows"] == 1 and s["files"]["outside"] == 1
    assert s["through"] == "2026-11-21T13:00:00Z" and list(s["by_page"]) == ["closing_SOCCER_2026-11-21T1230Z.json"]
    code, out = run(world, "--through", "2026-11-21T12:30:00Z")          # a run start exactly at --through: outside
    assert code == 0 and summary(out)["pages"] == 0 and summary(out)["files"]["outside"] == 2


@pytest.mark.parametrize("h,name", [(-0.01, "under 0 h (after the export)"), (0.0, "0-1 h"), (0.999, "0-1 h"),
                                    (1.0, "1-2 h"), (2.0, "2-3 h"), (3.0, "3-6 h"), (5.999, "3-6 h"),
                                    (6.0, "6-12 h"), (12.0, "12 h or more")])
def test_bucket_edges(h, name):
    assert rc.bucket(h) == name


def _add_match(db: Path, mid: int, like: int, ko: str | None = None, snaps=()):
    """A stored match with `like`'s teams (and its kickoff unless `ko`), and its api_football sessions:
    [(captured_at, {sel: devig})]."""
    eng = create_engine(f"sqlite:///{db}")
    with eng.begin() as c:
        cols = [r[1] for r in c.execute(text("PRAGMA table_info(matches)"))]
        keep = [k for k in cols if k != "id"]
        c.execute(text(f"INSERT INTO matches (id, {', '.join(keep)}) SELECT :n, {', '.join(keep)} FROM matches "
                       "WHERE id = :o"), {"n": mid, "o": like})
        if ko is not None:
            c.execute(text("UPDATE matches SET utc_date = :k WHERE id = :n"),
                      {"k": _dt(ko).strftime("%Y-%m-%d %H:%M:%S.%f"), "n": mid})
        for at, legs in snaps:
            for sel, v in legs.items():
                c.execute(text("INSERT INTO odds_snapshots (match_id, market, selection, devig_prob, n_books, "
                               "captured_at, source) VALUES (:m, '1X2', :s, :v, 5, :a, 'api_football')"),
                          {"m": mid, "s": sel, "v": v, "a": _dt(at).strftime("%Y-%m-%d %H:%M:%S.%f")})
    eng.dispose()


def test_a_page_id_naming_another_game_or_kickoff_is_never_used(world, tmp_path):
    ex = tmp_path / "ex_id"
    closing(ex, D + "15:00:00", EXP_1500, [row(100, X1, teams=("Bournemouth", "Sunderland")),
                                           row(100, X1, ko=D + "17:30:00")])
    code, out = run(world, ex=ex)
    assert code == 0
    lines = [ln for ln in out if ln.startswith("  ") and " · match 100 " in ln]
    assert len(lines) == 2
    assert lines[0].startswith("  2026-11-21 15:00:00Z · match 100 Bournemouth v Sunderland")
    assert ("on the copy: by both team names and the kickoff (the page's id 100 is Chelsea v Arsenal on the copy)"
            in lines[0])
    assert ("on the copy: match not found in the copy (the page's id 100 kicks off 2026-11-21 15:00:00" in lines[1]
            and "no stored match with both team names and the kickoff)" in lines[1])
    i = out.index(lines[0])
    assert "priced session captured 2026-11-21 14:25:10Z · stamp 2026-11-21 14:20:00Z" in out[i + 1]   # 107's
    s = summary(out)
    assert s["status"] == {"priced": 1, "match not found in the copy": 1}


def test_two_stored_matches_with_the_teams_and_kickoff_are_refused(world, tmp_path):
    _add_match(world["db"], 120, 107)
    ex = tmp_path / "ex_amb"
    closing(ex, D + "15:00:00", EXP_1500, [row(999, X1, teams=("Bournemouth", "Sunderland"))])
    code, out = run(world, ex=ex)
    assert code == 0
    assert ("on the copy: match not found in the copy (the page's id 999 is not in the copy; 2 stored matches share "
            "the teams and kickoff, none used)") in block(out, 999)
    assert summary(out)["status"] == {"match not found in the copy": 1}


def test_an_incomplete_session_whose_legs_differ_ends_the_run(world, tmp_path):
    """An incomplete session between two complete ones whose present legs carry another price ends the run (law 4:
    never counted through); one whose present legs agree does not."""
    h, a = dict(zip(SELS, X1)), dict(zip(SELS, X2))
    _add_match(world["db"], 130, 100, snaps=[(T1100, h), (T1205, {"HOME": a["HOME"], "AWAY": a["AWAY"]}), (T1425, h)])
    _add_match(world["db"], 131, 101, snaps=[(T1100, h), (T1205, {"HOME": h["HOME"], "AWAY": h["AWAY"]}), (T1425, h)])
    _add_match(world["db"], 132, 102, snaps=[(T1100, h), (T1205, {"HOME": h["HOME"]}), (T1205, {"HOME": a["HOME"]}),
                                             (T1425, h)])                     # two values for one leg
    _add_match(world["db"], 133, 103, snaps=[(T1100, h), (T1205, {"HOME": X1B[0]}), (T1425, h)])   # below rounding
    ex = tmp_path / "ex_gap"
    closing(ex, D + "15:00:00", EXP_1500, [row(m, X1, teams=GAMES[like][:2])
                                           for m, like in ((130, 100), (131, 101), (132, 102), (133, 103))])
    code, out = run(world, ex=ex)
    assert code == 0 and summary(out)["status"] == {"priced": 4}
    b = block(out, 130)
    assert "on the copy: by the page's match id (teams and kickoff agree)" in b
    assert "last-change age 2 min (identical as stored across 1 session(s) from 2026-11-21 14:25:10Z)" in b
    assert "at 4 places" not in b and "fresh (the triple moved at this fetch)" in b
    assert "incomplete sessions skipped 1" in b
    b = block(out, 131)
    assert "last-change age at least 206 min (identical as stored across 2 session(s) from 2026-11-21 11:00:35Z)" in b
    assert "stamp unknown in the run (M3 and M4 not told apart; 2 sessions, triple unchanged)" in b
    b = block(out, 132)
    assert "identical as stored across 1 session(s)" in b and "at 4 places" not in b
    b = block(out, 133)
    assert "last-change age 2 min (identical as stored across 1 session(s)" in b
    assert "at 4 places at least 206 min (2 sessions from 2026-11-21 11:00:35Z" in b


@pytest.mark.parametrize("flags", [["--from", "2026-11-21T13:00"], ["--through", "2026-11-21 13:00:00Z"],
                                   ["--from", "2026-11-22T00:00:00Z", "--through", "2026-11-21T00:00:00Z"]])
def test_a_bad_bound_is_refused_exit_2(world, flags):
    code, out = run(world, *flags)
    assert code == 2 and len(out) == 1 and out[0].startswith("REFUSED: ")


# ---- the fence (addendum 198 item 6(ii); #688's set) --------------------------------------------------------------

def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_a_read_leaves_the_copys_bytes_unchanged(world):
    before = _sha(world["db"])
    code, out = run(world)
    assert code == 0 and _sha(world["db"]) == before
    assert f"database --db {world['db'].resolve()} (mode=ro + immutable=1 URI, mode=ro&immutable=1" in out[0]
    assert sorted(x.name for x in world["db"].parent.iterdir() if x.name.startswith("copy.db")) == ["copy.db"]


def test_a_fresh_wal_backup_copy_opens_immutable_and_leaves_no_sidecar(world, tmp_path):
    live = tmp_path / "wal-live.db"
    with sqlite3.connect(world["db"]) as src, sqlite3.connect(live) as dst:
        src.backup(dst)
    with sqlite3.connect(live) as dst:
        dst.execute("PRAGMA journal_mode=WAL")
    d = tmp_path / "walcopy"
    d.mkdir()
    p = d / "sp.db"
    src = sqlite3.connect(live)
    bk = sqlite3.connect(p)
    src.backup(bk)
    bk.close()
    src.close()
    assert sorted(x.name for x in d.iterdir()) == ["sp.db"] and p.read_bytes()[18:20] == bytes([2, 2])
    before = _sha(p)
    code, out = run(world, db=p)
    assert code == 0 and summary(out)["rows"] == 11
    assert sorted(x.name for x in d.iterdir()) == ["sp.db"] and _sha(p) == before


def test_the_app_s_configured_database_as_db_is_refused(world, monkeypatch):
    from src.walters import mlb_pitchers_gate as mp
    monkeypatch.setattr(mp, "_app_db", lambda: world["db"].resolve())
    monkeypatch.setattr(rc, "read_pages", lambda *a, **k: pytest.fail("a closing page was read"))
    code, out = run(world)
    assert code == 2 and len(out) == 1 and out[0].startswith("REFUSED: --db ")
    assert "the app's configured database" in out[0] and out[0].endswith("nothing read")


def test_the_db_copy_refuses_a_write(world):
    from sqlalchemy.exc import OperationalError
    before = _sha(world["db"])
    with rc.open_db(rc.check_copy(str(world["db"]))) as (s, _label):
        with pytest.raises(OperationalError, match="readonly"):
            s.execute(text("CREATE TABLE t446 (x INTEGER)"))
    assert _sha(world["db"]) == before


def test_a_sidecar_beside_the_copy_is_refused(world):
    side = world["db"].with_name(world["db"].name + "-wal")
    side.write_bytes(b"")
    code, out = run(world)
    assert code == 2 and len(out) == 1 and "has a -wal sidecar" in out[0] and out[0].endswith("nothing read")


@pytest.mark.parametrize("db", [None, "", "  "])
def test_db_missing_is_refused_exit_2_nothing_read(world, monkeypatch, db):
    from src.db import database
    monkeypatch.setattr(database, "readonly_scope", lambda: pytest.fail("the configured database was opened"))
    monkeypatch.setattr(rc, "read_pages", lambda *a, **k: pytest.fail("a closing page was read"))
    out = []
    argv = ["--exports", str(world["ex"])] + ([] if db is None else ["--db", db])
    assert rc.main(argv, echo=out.append) == 2
    assert len(out) == 1 and out[0].startswith("REFUSED: --db is required") and out[0].endswith("nothing read")


@pytest.mark.parametrize("content", [b"not a sqlite file\n" * 64, b""], ids=["text", "empty"])
def test_a_db_that_is_not_a_readable_copy_is_refused(world, monkeypatch, content):
    bad = world["tmp"] / "not_a_copy.db"
    bad.write_bytes(content)
    monkeypatch.setattr(rc, "read_pages", lambda *a, **k: pytest.fail("a closing page was read"))
    code, out = run(world, db=bad)
    assert code == 2 and len(out) == 1
    assert out[0].startswith(f"REFUSED: --db {bad.resolve()}: cannot be read through a mode=ro + immutable=1 URI (")
    assert out[0].endswith("; nothing read") and not out[0].endswith("nothing read; nothing read")
    assert bad.read_bytes() == content


def test_db_under_data_is_refused_never_created(world, monkeypatch):
    monkeypatch.setattr(rc, "ROOT", world["tmp"])
    target = world["tmp"] / "data" / "sp_backup_test_446.db"
    code, out = run(world, db=target)
    assert code == 2 and out[0].startswith("REFUSED: --db") and "under data/" in out[0] and not target.exists()


def test_a_missing_db_is_refused_never_created(world):
    missing = world["tmp"] / "nope.db"
    code, out = run(world, db=missing)
    assert code == 2 and "REFUSED: no DB file" in out[0] and not missing.exists()


def test_a_missing_column_is_refused(world):
    eng = create_engine(f"sqlite:///{world['db']}")
    with eng.begin() as c:
        c.execute(text("ALTER TABLE odds_snapshots DROP COLUMN n_books"))
    eng.dispose()
    code, out = run(world)
    assert code == 2 and out == ["REFUSED: columns n_books not in odds_snapshots (law 1); nothing read"]


def test_the_configured_database_path_is_absent():
    src = Path(rc.__file__).read_text()
    assert "readonly_scope" not in src and "has_source_time" not in src and "attach_source_times" not in src


def test_the_script_imports_no_src_db_module_at_import():
    code = ("import importlib.util, sys; sys.path.insert(0, %r); "
            "s = importlib.util.spec_from_file_location('m', %r); m = importlib.util.module_from_spec(s); "
            "s.loader.exec_module(m); print([k for k in sys.modules if k.startswith('src.db')])"
            % (str(ROOT), str(ROOT / "scripts" / "pl_closing_book_age_receipt.py")))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "[]"


# ---- the pages' folders and exit codes --------------------------------------------------------------------------

def test_latest_is_refused_and_never_read(world, tmp_path):
    host = tmp_path / "host"
    closing(host / "latest", D + "15:00:00", EXP_1500, [row(100, X1)])
    closing(host / "misc", D + "15:00:00", EXP_1500, [row(100, X1)])
    code, out = run(world, ex=host)
    assert code == 0 and summary(out)["rows"] == 0                     # latest/ and misc/ never read
    for ex in (host / "latest",):
        code, out = run(world, ex=ex)
        assert code == 2 and len(out) == 1 and out[0].startswith(f"REFUSED: --exports {ex}: a latest/ folder")
    (host / "2026-11-21").symlink_to(host / "latest", target_is_directory=True)
    code, out = run(world, ex=host)
    assert code == 2 and "resolves to" in out[0] and "a latest/ folder; latest/ is never read" in out[0]


def test_exports_not_a_directory_is_refused(world):
    code, out = run(world, ex=world["tmp"] / "nowhere")
    assert code == 2 and out[0].startswith("REFUSED: --exports") and "not a directory" in out[0]


def test_exports_is_required(world):
    with pytest.raises(SystemExit) as e:
        rc.main(["--db", str(world["db"])], echo=lambda *_: None)
    assert e.value.code == 2


def test_an_unreadable_page_is_counted_never_fatal(world):
    (world["ex"] / "closing_SOCCER_2026-11-21T1730Z.json").write_text("{not json")
    code, out = run(world)
    s = summary(out)
    assert code == 0 and s["unreadable"] == ["closing_SOCCER_2026-11-21T1730Z.json"] and s["rows"] == 11


def test_a_partly_stamped_session_is_unknown_never_its_oldest(world):
    eng = create_engine(f"sqlite:///{world['db']}")
    with eng.begin() as c:
        assert c.execute(text("UPDATE odds_snapshots SET source_updated_at = NULL WHERE match_id = 107 AND "
                              "selection = 'DRAW'")).rowcount == 1
    eng.dispose()
    code, out = run(world)
    assert code == 0
    b = block(out, 999)
    assert "stamp unknown (the priced session's rows partly stamped)" in b
    assert "HEADLINE at least 2 min (by the last change)" in b
    assert summary(out)["measures"]["stamp"]["unknown"]["the priced session's rows partly stamped"] == 1


def test_pages_whose_run_start_is_unknown_are_never_re_pages_of_each_other(tmp_path):
    ex = tmp_path / "ex_unk"
    ex.mkdir()
    for name, rid, at in (("closing_SOCCER_a.json", "r0", D + "10:00:00Z"), ("closing_SOCCER_b.json", "r1",
                                                                            D + "11:00:00Z")):
        doc = {"exported_at": at, "git_sha": "x", "predictions": [row(100, X1)],
               "closing": {"family": "SOCCER", "run_id": rid}}
        (ex / name).write_text(json.dumps(doc))
    (ex / "closing_SOCCER_c.json").write_text((ex / "closing_SOCCER_a.json").read_text())
    pop = rc.read_pages(ex)
    got = [(g["file"], g["run"], g["repaged"], g["copy_of"]) for g in pop["pages"]]
    assert got == [("closing_SOCCER_a.json", None, None, None), ("closing_SOCCER_c.json", None, None,
                                                                 "closing_SOCCER_a.json"),
                   ("closing_SOCCER_b.json", None, None, None)]


def test_two_pages_with_no_run_id_and_no_exported_at_are_never_one_copy(tmp_path):
    ex = tmp_path / "ex_bare"
    ex.mkdir()
    for name, mid in (("closing_SOCCER_p.json", 100), ("closing_SOCCER_q.json", 101)):
        doc = {"git_sha": "x", "predictions": [row(mid, X1)],
               "closing": {"family": "SOCCER", "start": D + "15:00:00Z"}}
        (ex / name).write_text(json.dumps(doc))
    pop = rc.read_pages(ex)
    assert len({g["run"] for g in pop["pages"]}) == 1 and pop["pages"][0]["run"] is not None
    assert [g["copy_of"] for g in pop["pages"]] == [None, None]
    assert [g["repaged"] for g in pop["pages"]] == [(1, 2), (2, 2)]


def test_no_bookmaker_name_is_printed(world):
    _code, out = run(world)
    assert "SecretBook" not in "\n".join(out)
