"""#1102 PR1, THE FIELDS (ARCHITECT 2026-11-25, addenda 529 item 3(a), 532 item 2, 534 item 4; DEV 3's one text,
comment 7167846609), on an isolated throwaway DB:

- F1 `run_started_at`, top level: the slate run's held start, ISO Z with microseconds, verbatim; no key without
  `--run-start`, an option of export-predictions and export-nfl-predictions only (a bad value exits 2).
- F2 `market.books_captured_at`, the priced block: the OLDEST capture of the last 1X2 session before kickoff, every row
  of it (incomplete books too), as the closing watch's price_captures reads its books (C:1176).
- F3 `kalshi_legs_captured_at` beside kalshi_legs: each leg's last capture before kickoff, mismatched dropped, null
  with kalshi_legs, never {} (C:1168-1175).
- F4 `market.books_source_updated_at`, exactly where F2 is: close.book_stamp on the same close: the oldest provider
  stamp over the rows it priced; one unstamped makes it null; null on every MLB row (#628).
F2-F4 ISO Z, whole seconds. Stamps only: no age is written (532 item 2)."""
import json
import re
import sqlite3
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from click.testing import CliRunner
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.db.schema import Sport

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy" / "hosting"))
import closing as mc  # noqa: E402

Z_SECONDS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
FIELDS = ("run_started_at", "books_captured_at", "books_source_updated_at", "kalshi_legs_captured_at")


@pytest.fixture
def iso(tmp_path, monkeypatch):
    """A throwaway DB with the (unmapped) stamp columns added, as migrate_odds_source_updated_at.py would (the #615
    fixture's pattern); the closing watch reads the same file through sqlite3."""
    from src.db import database
    from src.db.schema import Base
    path = tmp_path / "iso.db"
    eng = create_engine(f"sqlite:///{path}", future=True)
    Base.metadata.create_all(eng)
    with eng.begin() as c:
        for t in ("odds", "odds_snapshots"):
            c.execute(text(f"ALTER TABLE {t} ADD COLUMN source_updated_at DATETIME"))
    monkeypatch.setattr(database, "SessionLocal",
                        sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True, expire_on_commit=False))
    monkeypatch.setattr(database, "_engine", eng)
    monkeypatch.chdir(tmp_path)
    yield NS(path=path, tmp=tmp_path)
    eng.dispose()


def _ko():
    from src.timeutil import utc_now_naive
    return utc_now_naive().replace(microsecond=0) + timedelta(days=2)


def _match(s, key, ko, sport, code):
    from src.db.schema import Competition, Match, MatchStatus, Prediction, Team
    c = s.query(Competition).filter_by(code=code).one_or_none()
    if c is None:
        c = Competition(sport=sport, code=code, name=code, area="X", type="LEAGUE")
        s.add(c)
        s.flush()
    h, a = Team(sport=sport, name=f"CF {key} H"), Team(sport=sport, name=f"CF {key} A")
    s.add_all([h, a])
    s.flush()
    m = Match(sport=sport, competition_id=c.id, season="2026", utc_date=ko, status=MatchStatus.SCHEDULED,
              home_team_id=h.id, away_team_id=a.id)
    s.add(m)
    s.flush()
    s.add(Prediction(match_id=m.id, model_version="t", home_win_prob=0.5,
                     draw_prob=0.25 if sport == Sport.SOCCER else None,
                     away_win_prob=0.25 if sport == Sport.SOCCER else 0.5))
    return m


def _odds(s, m, rows):
    """rows: (bookmaker, selection, price, captured_at, provider stamp | None)."""
    from src.db.database import write_source_times
    from src.db.schema import Odds
    made = []
    for bk, sel, px, at, _ in rows:
        o = Odds(match_id=m.id, bookmaker=bk, market="1X2", selection=sel, price_decimal=px, captured_at=at,
                 source="test")
        s.add(o)
        made.append(o)
    s.flush()
    write_source_times(s, "odds", [(o.id, r[4]) for o, r in zip(made, rows)])


def _kalshi(s, m, legs):
    """legs: (selection, captured_at)."""
    from src.db.schema import OddsSnapshot
    for sel, at in legs:
        s.add(OddsSnapshot(match_id=m.id, market="ML", selection=sel, devig_prob=0.4, n_books=1, captured_at=at,
                           source="kalshi", yes_bid=0.39, yes_ask=0.41))
    s.flush()


def _captures(iso, mid, ko):
    """The closing watch's own read (R2's, C:1158-1177), with its kickoff as its stored schedule gives it."""
    con = sqlite3.connect(str(iso.path))
    try:
        return mc.price_captures(con, mid, mc.parse_utc(mc.iso_z(ko)))
    finally:
        con.close()


def _soccer_world(s, ko, key="soc", stamps=True):
    """The last 1X2 session (within 10 min of its newest capture): an INCOMPLETE book (HOME only) captured first and
    stamped oldest, then two complete books; an older session 3 h before. Kalshi: three legs, each with an older and a
    newer pre-kickoff capture (the newer with a fraction), and one in-play capture that never counts."""
    m = _match(s, key, ko, Sport.SOCCER, "CFSOC")
    h = lambda mins: ko - timedelta(minutes=mins)
    st = (lambda hrs: ko - timedelta(hours=hrs)) if stamps else (lambda hrs: None)
    _odds(s, m, [("bkold", sel, 3.0, h(180), st(40)) for sel in ("HOME", "DRAW", "AWAY")]
          + [("bkI", "HOME", 2.0, h(65), st(50))]
          + [("bk1", sel, px, h(62), st(30)) for sel, px in (("HOME", 2.1), ("DRAW", 3.4), ("AWAY", 3.6))]
          + [("bk2", sel, px, h(60), st(36)) for sel, px in (("HOME", 2.0), ("DRAW", 3.5), ("AWAY", 3.8))])
    newer = h(30) + timedelta(seconds=0.987654)
    _kalshi(s, m, [(sel, h(120)) for sel in ("HOME", "DRAW", "AWAY")]
            + [(sel, newer) for sel in ("HOME", "DRAW", "AWAY")]
            + [(sel, ko + timedelta(minutes=5)) for sel in ("HOME", "DRAW", "AWAY")])
    return m


def _export(sport, code, ko, **kw):
    from src.walters.export import export_predictions
    doc = json.loads(export_predictions(sport=sport, start_date=ko - timedelta(days=1),
                                        end_date=ko + timedelta(days=1), competition_code=code, **kw))
    return doc, {r["match_id"]: r for r in doc["predictions"]}


# ------------------------------------------------------------------------------------------------------ F2, F3, F4 ---

def test_soccer_row_carries_the_three_stamps_as_the_closing_watch_reads_them(iso):
    from src.db.database import session_scope
    ko = _ko()
    with session_scope() as s:
        mid = _soccer_world(s, ko).id
    doc, rows = _export(Sport.SOCCER, "CFSOC", ko)
    row, caps = rows[mid], _captures(iso, mid, ko)
    mk = row["market"]
    assert mk["bookmaker_count"] == 2                                       # the priced block
    assert mk["books_captured_at"] == mc.iso_z(caps["books"]) == mc.iso_z(ko - timedelta(minutes=65))   # F2 == C
    assert mk["books_source_updated_at"] == mc.iso_z(ko - timedelta(hours=36))   # F4: bk2's, oldest PRICED; never bkI
    legs = {sel: mc.iso_z(t) for sel, t in caps["kalshi_legs"].items()}
    assert row["kalshi_legs_captured_at"] == legs                          # F3 == C, leg by leg
    assert set(row["kalshi_legs_captured_at"]) == set(row["kalshi_legs"]) == {"HOME", "DRAW", "AWAY"}
    assert set(legs.values()) == {mc.iso_z(ko - timedelta(minutes=30))}    # the newer, its fraction cut; never in-play
    for v in (mk["books_captured_at"], mk["books_source_updated_at"], *row["kalshi_legs_captured_at"].values()):
        assert Z_SECONDS.match(v), v
    assert "run_started_at" not in doc                                      # F1: no --run-start, no key


def test_f4_is_book_stamp_on_the_same_close_not_the_fixture_rows_all_rows_reading(iso):
    from src.db.database import attach_source_times, session_scope
    from src.db.schema import Odds
    from src.timeutil import iso_z_seconds, oldest_source_time
    from src.walters.close import THREE_WAY, book_stamp, close_1x2
    ko = _ko()
    with session_scope() as s:
        mid = _soccer_world(s, ko).id
        odds = list(s.query(Odds).filter(Odds.match_id == mid))
        cl = close_1x2(odds, ko, THREE_WAY)
        want = iso_z_seconds(book_stamp(cl, s))
        all_rows = iso_z_seconds(oldest_source_time(attach_source_times(s, cl["rows"])))   # E:1234's reading
    _, rows = _export(Sport.SOCCER, "CFSOC", ko)
    assert rows[mid]["market"]["books_source_updated_at"] == want == mc.iso_z(ko - timedelta(hours=36))
    assert all_rows == mc.iso_z(ko - timedelta(hours=50)) != want          # the incomplete book is in that one only


def test_one_unstamped_priced_row_makes_f4_null_and_f2_stands(iso):
    from src.db.database import session_scope
    ko = _ko()
    with session_scope() as s:
        m = _match(s, "unst", ko, Sport.SOCCER, "CFSOC")
        h = lambda mins: ko - timedelta(minutes=mins)
        _odds(s, m, [("bk1", sel, px, h(62), ko - timedelta(hours=30)) for sel, px in
                     (("HOME", 2.1), ("DRAW", 3.4), ("AWAY", 3.6))]
              + [("bk2", "HOME", 2.0, h(60), ko - timedelta(hours=30)), ("bk2", "DRAW", 3.5, h(60), None),
                 ("bk2", "AWAY", 3.8, h(60), ko - timedelta(hours=30))])
        mid = m.id
    _, rows = _export(Sport.SOCCER, "CFSOC", ko)
    mk = rows[mid]["market"]
    assert mk["books_source_updated_at"] is None                           # unknown, never fresh (law 4)
    assert mk["books_captured_at"] == mc.iso_z(_captures(iso, mid, ko)["books"]) == mc.iso_z(ko - timedelta(minutes=62))


def test_a_complete_stamped_book_beside_an_incomplete_unstamped_one_gives_the_stamp(iso):
    from src.db.database import session_scope
    ko = _ko()
    with session_scope() as s:
        m = _match(s, "half", ko, Sport.SOCCER, "CFSOC")
        h = lambda mins: ko - timedelta(minutes=mins)
        _odds(s, m, [("bk1", sel, px, h(60), ko - timedelta(hours=30)) for sel, px in
                     (("HOME", 2.1), ("DRAW", 3.4), ("AWAY", 3.6))]
              + [("bkI", "HOME", 2.0, h(61), None), ("bkI", "AWAY", 3.7, h(61), None)])   # no DRAW: incomplete
        mid = m.id
    _, rows = _export(Sport.SOCCER, "CFSOC", ko)
    mk = rows[mid]["market"]
    assert mk["bookmaker_count"] == 1 and mk["books_source_updated_at"] == mc.iso_z(ko - timedelta(hours=30))
    assert mk["books_captured_at"] == mc.iso_z(ko - timedelta(minutes=61))      # F2 counts the incomplete book


def test_mlb_rows_carry_no_provider_stamp_628(iso):
    """api_baseball sends no update time (#628): the stored rows carry none, so F4 is null on every MLB row with no
    special case; F2 is the board's own capture."""
    from src.db.database import session_scope
    from src.ingestion.service import _mlb_store_odds
    ko = _ko()
    board = [NS(market="1X2", selection=sel, bookmaker=bk, price_decimal=px, line=None)       # OddsRow: no stamp
             for bk, sel, px in (("bk1", "HOME", 1.8), ("bk1", "AWAY", 2.1), ("bk2", "HOME", 1.9), ("bk2", "AWAY", 2.0))]
    with session_scope() as s:
        m = _match(s, "mlb", ko, Sport.MLB, "CFMLB")
        assert _mlb_store_odds(s, m, board)[0] == 4
        mid = m.id
    _, rows = _export(Sport.MLB, "CFMLB", ko)
    mk = rows[mid]["market"]
    assert mk["bookmaker_count"] == 2 and mk["books_source_updated_at"] is None
    assert mk["books_captured_at"] == mc.iso_z(_captures(iso, mid, ko)["books"]) and Z_SECONDS.match(
        mk["books_captured_at"])
    assert rows[mid]["kalshi_legs"] is None and rows[mid]["kalshi_legs_captured_at"] is None   # no Kalshi: null, not {}


def test_the_book_stamps_sit_on_the_priced_block_only(iso):
    """F2 and F4 exist where bookmaker_count > 0 and nowhere else: not on the unpriced block, not on a Kalshi-only
    block; no age is written anywhere (532 item 2)."""
    from src.db.database import session_scope
    ko = _ko()
    with session_scope() as s:
        un = _match(s, "unpriced", ko, Sport.SOCCER, "CFSOC")
        _odds(s, un, [("bk1", "HOME", 2.1, ko - timedelta(minutes=60), ko - timedelta(hours=30))])
        ko_only = _match(s, "konly", ko, Sport.SOCCER, "CFSOC")
        _kalshi(s, ko_only, [(sel, ko - timedelta(minutes=30)) for sel in ("HOME", "DRAW", "AWAY")])
        ids = (un.id, ko_only.id)
    doc, rows = _export(Sport.SOCCER, "CFSOC", ko)
    for mid in ids:
        mk = rows[mid]["market"]
        assert mk["bookmaker_count"] == 0
        assert "books_captured_at" not in mk and "books_source_updated_at" not in mk
    assert rows[ids[1]]["kalshi_legs_captured_at"] == {sel: mc.iso_z(ko - timedelta(minutes=30))
                                                       for sel in ("HOME", "DRAW", "AWAY")}
    assert rows[ids[0]]["kalshi_legs_captured_at"] is None and rows[ids[0]]["kalshi_legs"] is None
    assert not re.search(r'_age[a-z_]*"\s*:', json.dumps(doc))              # stamps only


def test_a_mismatched_games_legs_are_dropped_with_kalshi_legs(iso, monkeypatch):
    from src.db.database import session_scope
    from src.walters import kalshi_legs as kl
    ko = _ko()
    with session_scope() as s:
        mid = _soccer_world(s, ko, key="mm").id
    monkeypatch.setattr(kl, "mismatched", lambda conn, ids, captured_from=None: {mid: ["EV-A", "EV-B"]})
    _, rows = _export(Sport.SOCCER, "CFSOC", ko)
    assert rows[mid]["kalshi_legs"] is None and rows[mid]["kalshi_legs_captured_at"] is None


def test_f3_keeps_kalshi_legs_keys_and_a_leg_of_unknown_capture_is_null():
    """A leg whose capture is unknown (a legacy DB only: the ORM column is NOT NULL) stays, null (law 4); the keys
    are kalshi_legs' keys; nothing captured is null, never {}."""
    from datetime import datetime
    from src.walters.venue import kalshi_legs_captured_at
    at = datetime(2026, 11, 25, 16, 0, 9, 987654)
    assert kalshi_legs_captured_at({"HOME": NS(captured_at=at), "AWAY": NS(captured_at=None)}) == {
        "AWAY": None, "HOME": "2026-11-25T16:00:09Z"}
    assert kalshi_legs_captured_at({}) is None and kalshi_legs_captured_at(None) is None


# ------------------------------------------------------------------------------------------------------------ NFL ---

def test_the_nfl_file_carries_the_same_fields(iso, tmp_path):
    from src.db.database import session_scope
    from src.walters.nfl_predict import export_nfl_predictions
    ko = _ko()
    with session_scope() as s:
        m = _match(s, "nfl", ko, Sport.NFL, "NFL")
        h = lambda mins: ko - timedelta(minutes=mins)
        _odds(s, m, [("bk1", "HOME", 1.8, h(62), ko - timedelta(hours=20)), ("bk1", "AWAY", 2.1, h(62), ko - timedelta(hours=20)),
                     ("bk2", "HOME", 1.9, h(60), ko - timedelta(hours=26)), ("bk2", "AWAY", 2.0, h(60), ko - timedelta(hours=26))])
        _kalshi(s, m, [("HOME", h(40)), ("AWAY", h(41))])
        mid = m.id
    run = "2026-11-25T16:00:09.123456Z"
    doc = json.loads(open(export_nfl_predictions(days_ahead=8, out_dir=str(tmp_path / "e"),
                                                 run_started_at=run)).read())
    row = {r["match_id"]: r for r in doc["predictions"]}[mid]
    caps = _captures(iso, mid, ko)
    assert doc["run_started_at"] == run and list(doc).index("run_started_at") == 1     # verbatim, beside exported_at
    assert row["market"]["books_captured_at"] == mc.iso_z(caps["books"]) == mc.iso_z(h(62))
    assert row["market"]["books_source_updated_at"] == mc.iso_z(ko - timedelta(hours=26))
    assert row["kalshi_legs_captured_at"] == {sel: mc.iso_z(t) for sel, t in caps["kalshi_legs"].items()} == {
        "AWAY": mc.iso_z(h(41)), "HOME": mc.iso_z(h(40))}
    plain = json.loads(open(export_nfl_predictions(days_ahead=8, out_dir=str(tmp_path / "p"))).read())
    assert "run_started_at" not in plain


# ------------------------------------------------------------------------------------------------------------- F1 ---

def test_f1_is_written_verbatim_at_the_top_and_only_when_given(iso):
    from src.db.database import session_scope
    ko = _ko()
    with session_scope() as s:
        _soccer_world(s, ko, key="f1")
    run = "2026-11-25T16:00:09.000000Z"
    with_f1, _ = _export(Sport.SOCCER, "CFSOC", ko, run_started_at=run)
    without, _ = _export(Sport.SOCCER, "CFSOC", ko)
    assert with_f1["run_started_at"] == run and list(with_f1).index("run_started_at") == 1
    assert "run_started_at" not in without


GOOD = "2026-11-25T16:00:09.123456Z"
BAD = ["2026-11-25T16:00:09Z", "2026-11-25T16:00:09.123456+00:00", "2026-11-25T16:00:09.1234567Z",
       "\uff12\uff10\uff12\uff16-11-25T16:00:09.123456Z",                  # fullwidth digits: ASCII only
       "2026-11-25 16:00:09.123456Z", "2026-13-25T16:00:09.123456Z", "", "junk"]


@pytest.mark.parametrize("cmd", ["export-predictions", "export-nfl-predictions"])
@pytest.mark.parametrize("bad", BAD)
def test_a_bad_run_start_exits_2_before_any_read(cmd, bad, monkeypatch):
    import cli
    from src.walters import export as ex
    from src.walters import nfl_predict as nf
    touched = []
    monkeypatch.setattr(ex, "export_predictions", lambda **k: touched.append(k) or "{}")
    monkeypatch.setattr(nf, "export_nfl_predictions", lambda **k: touched.append(k) or "x")
    args = [cmd, *(["--sport", "mlb"] if cmd == "export-predictions" else []), "--run-start", bad]
    r = CliRunner().invoke(cli.cli, args)
    assert r.exit_code == 2 and touched == [], r.output


@pytest.mark.parametrize("cmd", ["export-predictions", "export-nfl-predictions"])
def test_a_good_run_start_reaches_the_export_verbatim(cmd, monkeypatch, tmp_path):
    import cli
    from src.walters import export as ex
    from src.walters import nfl_predict as nf
    seen = []
    monkeypatch.setattr(ex, "export_predictions", lambda **k: seen.append(k["run_started_at"]) or "{}")
    monkeypatch.setattr(nf, "export_nfl_predictions", lambda **k: seen.append(k["run_started_at"]) or "x")
    monkeypatch.chdir(tmp_path)
    args = [cmd, *(["--sport", "mlb", "--days", "1"] if cmd == "export-predictions" else []), "--run-start", GOOD,
            "--out", str(tmp_path / "o.json")]
    r = CliRunner().invoke(cli.cli, args)
    assert seen == [GOOD], r.output


def test_run_start_with_csv_exits_2_a_csv_has_no_top_level(monkeypatch):
    import cli
    from src.walters import export as ex
    touched = []
    monkeypatch.setattr(ex, "export_predictions", lambda **k: touched.append(k) or "")
    r = CliRunner().invoke(cli.cli, ["export-predictions", "--sport", "mlb", "--format", "csv", "--run-start", GOOD])
    assert r.exit_code == 2 and touched == [], r.output


def test_only_the_two_prediction_exports_take_a_run_start():
    import cli
    have = sorted(name for name, c in cli.cli.commands.items() if any(p.name == "run_start" for p in c.params))
    assert have == ["export-nfl-predictions", "export-predictions"]


def test_no_chain_passes_a_run_start_only_the_slate_stage_does():
    """The closings, the freshen chains and the MLB closing run pass none (H/chains.py); the slate's export step alone
    gains it (526 Q1), and the closing's export (resolve_steps) carries none."""
    import chains
    for name, ch in chains.CHAINS.items():
        for step in ch["steps"]:
            assert "--run-start" not in step, (name, step)
    from datetime import datetime, timezone
    games = [{"match_id": 1, "start": datetime(2026, 11, 29, 18, tzinfo=timezone.utc)}]
    at = datetime(2026, 11, 29, 13, 30, 0, 250000, tzinfo=timezone.utc)
    for fam in mc.FAMILIES:
        clo = mc.resolve_steps(fam, games[0]["start"], games, at, "RID")
        assert not any("--run-start" in s for s in clo)
        exp = mc.slate_steps(fam, games[0]["start"].date(), games, at, "RID")[-1]
        i = exp.index("--run-start")
        assert exp[i + 1] == "2026-11-29T13:30:00.250000Z" and exp[i + 2] == "--out"


def test_the_fixture_rows_carry_none_of_the_four(iso, tmp_path):
    """Seen: fixture rows (E:1204), and with them window_24h.json and the intl files built from them: none."""
    from src.db.database import session_scope
    from src.walters.export import export_fixtures
    ko = _ko()
    with session_scope() as s:
        _soccer_world(s, ko, key="fx")
    path = export_fixtures("CFSOC", out_dir=str(tmp_path / "fx"))
    body = open(path).read() if isinstance(path, str) and Path(path).exists() else json.dumps(path)
    for name in FIELDS:
        assert f'"{name}"' not in body, name


def test_the_one_named_edge_a_fraction_at_the_session_boundary(iso):
    """Named, not hidden (the review of #1102 PR1): the watch cuts each stored capture to the second before it forms
    the session (closing.parse_utc); the export's close reads full precision. Captures 10 min 0.2 s apart, the older
    with a fraction, are one session to the watch and two to the close, so F2 is the newer book's there and the older
    one's in the watch. At whole-second captures (every other test here) the two agree."""
    from src.db.database import session_scope
    ko = _ko()
    t = ko - timedelta(hours=2)
    with session_scope() as s:
        m = _match(s, "edge", ko, Sport.MLB, "CFEDGE")
        _odds(s, m, [("bkA", "HOME", 1.8, t + timedelta(seconds=0.3), None),
                     ("bkA", "AWAY", 2.1, t + timedelta(seconds=0.3), None),
                     ("bkB", "HOME", 1.9, t + timedelta(minutes=10, seconds=0.5), None),
                     ("bkB", "AWAY", 2.0, t + timedelta(minutes=10, seconds=0.5), None)])
        mid = m.id
    _, rows = _export(Sport.MLB, "CFEDGE", ko)
    assert rows[mid]["market"]["books_captured_at"] == mc.iso_z(t + timedelta(minutes=10))   # the close: bkB alone
    assert mc.iso_z(_captures(iso, mid, ko)["books"]) == mc.iso_z(t)                          # the watch: both books
