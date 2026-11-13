"""addendum 370 item 1 (lane nhl, #105): scripts/nhl_landing_agreement_receipt.py reads, from a .backup copy, how often
and how early the NHL landing page's projected_starter is the game's eventual_starter. Read-only; counts and shares,
no threshold. Each test builds its own SQLite file under tmp_path: the shared test database is never written."""
import hashlib
import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.availability import nhl_landing as nl

PREGAME = [label for label, _ in nl.PREGAME]
DAY1 = datetime(2026, 11, 12, 0, 0)          # NHL day 2026-11-11 (before 10:00Z)
DAY2 = datetime(2026, 11, 13, 0, 30)         # NHL day 2026-11-12


def _script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "nhl_landing_agreement_receipt.py"
    spec = importlib.util.spec_from_file_location("nhl_landing_agreement_receipt", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Store:
    """Writes observations then their assertions, in the order the store's insert guards require (the newest
    observation alone receives assertions; recorded_at is its fetched_at)."""

    def __init__(self, path):
        from sqlalchemy import create_engine

        from src.db.schema import Base
        self.path = path
        self.eng = create_engine(f"sqlite:///{path}")
        Base.metadata.create_all(self.eng)

    def poll(self, gid, label, kickoff, status="complete", asserted=(), late=False):
        from sqlalchemy.orm import Session

        from src.db.schema import AvailabilityAssertion, AvailabilityObservation, Sport
        endpoint = nl.BOXSCORE if label == nl.EVENTUAL[0] else nl.LANDING
        offset = dict(nl.PREGAME).get(label, nl.EVENTUAL[1])
        at = kickoff - timedelta(minutes=offset)
        fetched = None if status == "missed" else at + timedelta(seconds=20)
        with Session(self.eng) as s:
            o = AvailabilityObservation(sport=Sport.NHL, source=nl.SOURCE, endpoint=nl.game_url(gid, endpoint),
                                        match_id=None, kickoff_at=kickoff, poll_label=label, scheduled_at=at,
                                        fetched_at=fetched, http_status=None if status == "missed" else 200,
                                        status=status, late=late, rows_asserted=len(asserted))
            s.add(o)
            s.flush()
            for kind, side, pid, extra in asserted:
                attrs = {"side": side, "source_match_id": str(gid), **extra}
                s.add(AvailabilityAssertion(observation_id=o.id, sport=Sport.NHL, kind=kind, player_id=None,
                                            source_player_id=str(pid), player_name=f"G{pid}", team_id=None,
                                            source_team=side.upper(), match_id=None, attrs=attrs,
                                            source_stamp=None, recorded_at=fetched))
            s.commit()

    def close(self):
        self.eng.dispose()


def proj(side, pid):
    return ("projected_starter", side, pid, {})


def ev(side, pid, **extra):
    return ("eventual_starter", side, pid, {"toi_seconds": 3600, "two_in_net": False, "toi_unread": 0, **extra})


def _world(tmp_path, name="copy.db"):
    """Five games:
    A (day 1): every poll complete; away names 31 throughout, 31 starts; home names 40 to T-45 then 41, 41 starts.
    B (day 1): T-120 missed, T-90 partial, T-60 asserts the away side only; T+20 has two in net at home.
    C (day 2): every landing complete (away 50 / home 60); no T+20 row.
    D (day 2): postponed: T-120 written against two starts a day apart; left out whole.
    E (day 2): T-0 missed; the eventual's toi unread at home; away names 70 then 71 at T-15, 70 starts."""
    st = Store(tmp_path / name)
    A, B, C, D, E = 2025020101, 2025020102, 2025020103, 2025020104, 2025020105
    for label in PREGAME:
        home = 40 if PREGAME.index(label) < PREGAME.index("T-35") else 41
        st.poll(A, label, DAY1, asserted=[proj("away", 31), proj("home", home)])
    st.poll(A, "T+20", DAY1, asserted=[ev("away", 31), ev("home", 41)])
    kb = DAY1 + timedelta(hours=1)
    for label in PREGAME:
        if label == "T-120":
            st.poll(B, label, kb, status="missed")
        elif label == "T-90":
            st.poll(B, label, kb, status="partial", asserted=[proj("away", 11), proj("home", 12)])
        elif label == "T-60":
            st.poll(B, label, kb, asserted=[proj("away", 11)])
        else:
            st.poll(B, label, kb, asserted=[proj("away", 11), proj("home", 12)], late=(label == "T-15"))
    st.poll(B, "T+20", kb, asserted=[ev("away", 11), ev("home", 12, two_in_net=True), ev("home", 13, two_in_net=True)])
    for label in PREGAME:
        st.poll(C, label, DAY2, asserted=[proj("away", 50), proj("home", 60)])
    st.poll(D, "T-120", DAY2, asserted=[proj("away", 80), proj("home", 90)])
    st.poll(D, "T-120", DAY2 + timedelta(days=1), asserted=[proj("away", 80), proj("home", 90)])
    ke = DAY2 + timedelta(hours=2)
    for label in PREGAME:
        if label == "T-0":
            st.poll(E, label, ke, status="missed")
        else:
            away = 71 if label == "T-15" else 70
            st.poll(E, label, ke, asserted=[proj("away", away), proj("home", 61)])
    st.poll(E, "T+20", ke, asserted=[ev("away", 70), ev("home", 61, toi_unread=1)])
    st.close()
    path = tmp_path / name
    assert not any(path.with_name(path.name + x).exists() for x in ("-wal", "-shm", "-journal"))
    return path, {"A": A, "B": B, "C": C, "D": D, "E": E}


def _run(mod, args, capsys):
    rc = mod.main(args)
    return rc, capsys.readouterr().out


def _tail(out):
    line = out.strip().splitlines()[-1]
    assert line.startswith("NHL-LANDING-AGREEMENT-RECEIPT ")
    return json.loads(line.split(" ", 1)[1])


def test_370_the_receipt_counts_agreement_per_label_from_the_copy_and_writes_nothing(tmp_path, capsys):
    mod = _script()
    copy, ids = _world(tmp_path)
    before = hashlib.sha256(copy.read_bytes()).hexdigest()
    rc, out = _run(mod, ["--db", str(copy)], capsys)
    assert rc == 0, out
    assert hashlib.sha256(copy.read_bytes()).hexdigest() == before
    assert not any(copy.with_name(copy.name + x).exists() for x in ("-wal", "-shm", "-journal"))
    t = _tail(out)
    assert t["games_stored"] == 5 and t["games_read"] == 4 and t["sides"] == 8
    assert t["series_left_out"] == [str(ids["D"])]
    # n per label: A's two sides always; B's away from T-90 on but T-90 is partial, so from T-60; B's home from T-45
    # (two in net: never); E's away while answered (home's toi unread: never); C has no eventual
    #   T-120: A2 + E1 = 3 (B missed)    T-90: A2 + E1 = 3 (B partial)   T-60: A2 + B away + E1 = 4
    #   T-45 .. T-15: 4 each             T-0: A2 + B away = 3 (E missed)
    want_n = {"T-120": 3, "T-90": 3, "T-60": 4, "T-45": 4, "T-35": 4, "T-30": 4, "T-15": 4, "T-0": 3}
    # agree: A's away always; A's home from T-35; B's away always; E's away except T-15
    want_agree = {"T-120": 2, "T-90": 2, "T-60": 3, "T-45": 3, "T-35": 4, "T-30": 4, "T-15": 3, "T-0": 3}
    assert {k: v[1] for k, v in t["per_label"].items()} == want_n
    assert {k: v[0] for k, v in t["per_label"].items()} == want_agree
    assert "  T-35: agree 4 of 4 · share 1.0000" in out
    assert "  T-120: agree 2 of 3 · share 0.6667" in out


def test_370_the_sides_left_out_carry_their_two_reasons(tmp_path, capsys):
    mod = _script()
    copy, _ = _world(tmp_path)
    rc, out = _run(mod, ["--db", str(copy)], capsys)
    assert rc == 0
    t = _tail(out)
    # 8 sides read per label: left out = 8 - n
    assert t["left_out"] == {"T-120": 5, "T-90": 5, "T-60": 4, "T-45": 4, "T-35": 4, "T-30": 4, "T-15": 4, "T-0": 5}
    assert "projection: missed poll · eventual: read" in out              # B away at T-120
    assert "projection: missed poll · eventual: two in net" in out        # B home at T-120
    assert "projection: partial poll · eventual: read" in out             # B away at T-90
    assert "projection: side not asserted · eventual: two in net" in out  # B home at T-60
    assert "projection: read · eventual: no T+20 row" in out              # C, every label
    assert "projection: read · eventual: toi unread" in out               # E home
    assert "projection: missed poll · eventual: read" in out              # E away at T-0
    assert "left out whole: game 2025020104: a label written more than once (T-120)" in out


def test_370_by_day_and_the_first_stable_label(tmp_path, capsys):
    mod = _script()
    copy, _ = _world(tmp_path)
    rc, out = _run(mod, ["--db", str(copy)], capsys)
    assert rc == 0
    lines = out.splitlines()
    d1 = next(x for x in lines if x.startswith("  2026-11-11 ") and "/" in x and "game" not in x)
    d2 = next(x for x in lines if x.startswith("  2026-11-12 ") and "/" in x and "game" not in x)
    # day 1 (A, B): A's home names 40 to T-45 (41 starts); B's away is n from T-60. Day 2 (C, E): C has no eventual,
    # E's home its toi unread, so only E's away is ever n: 70 to T-30, 71 at T-15, T-0 missed
    assert d1.split()[1:] == ["1/2=0.5000", "1/2=0.5000", "2/3=0.6667", "2/3=0.6667", "3/3=1.0000", "3/3=1.0000",
                              "3/3=1.0000", "3/3=1.0000"]
    assert d2.split()[1:] == ["1/1=1.0000"] * 6 + ["0/1=0.0000", "0/0=n/a"]
    t = _tail(out)
    # the first stable label, OBSERVED, walking back from T-0: A away runs to T-120 (agree); A home changes at T-45, so
    # T-35 (agree); C's two run to T-120 (no eventual). Gapped: B away's run stops at T-90 (partial), so T-60 at the
    # latest (agree); B home's at T-60 (not asserted), so T-45 (two in net: unread). E's two: T-0 missed, no run.
    assert t["first_stable"] == {"T-120": 3, "T-90": 0, "T-60": 0, "T-45": 0, "T-35": 1, "T-30": 0, "T-15": 0,
                                 "T-0": 0}
    assert t["first_stable_gap"] == {"T-120": 0, "T-90": 0, "T-60": 1, "T-45": 1, "T-35": 0, "T-30": 0, "T-15": 0,
                                     "T-0": 0}
    assert t["no_projection"] == 0 and t["no_t0"] == 2 and t["off_label"] == []
    assert "  T-120: 3 · agree 1 · differ 0 · eventual unread 2" in out
    assert "  T-35: 1 · agree 1 · differ 0 · eventual unread 0" in out
    assert "first stable T-60 at the latest (a label with no projection before it)" in out
    assert "first stable (no T-0 projection: not observed)" in out


def test_370_the_observations_are_counted_by_status_and_late(tmp_path, capsys):
    mod = _script()
    copy, _ = _world(tmp_path)
    rc, out = _run(mod, ["--db", str(copy)], capsys)
    assert rc == 0
    assert "  T-120: complete 3, missed 1 · late 0" in out
    assert "  T-90: complete 3, partial 1 · late 0" in out
    assert "  T-15: complete 4 · late 1" in out
    assert "  T-0: complete 3, missed 1 · late 0" in out
    assert "  T+20: complete 3, no row 1 · late 0" in out


def test_370_the_receipt_refuses_what_it_cannot_trust_and_reads_nothing(tmp_path, capsys):
    mod = _script()
    rc, out = _run(mod, [], capsys)
    assert rc == 2 and "REFUSED" in out
    copy, _ = _world(tmp_path)
    (tmp_path / "copy.db-wal").write_bytes(b"")
    rc, out = _run(mod, ["--db", str(copy)], capsys)
    assert rc == 2 and "-wal sidecar" in out and "nothing read" in out
    (tmp_path / "copy.db-wal").unlink()
    import sqlite3
    bare = tmp_path / "bare.db"
    con = sqlite3.connect(bare)
    con.execute("CREATE TABLE t (x)")
    con.commit()
    con.close()
    rc, out = _run(mod, ["--db", str(bare)], capsys)                     # not a database of this app at all
    assert rc == 2 and "REFUSED" in out and out.count("nothing read") == 1
    older = tmp_path / "older.db"                                        # the app's tables, the record's not yet
    con = sqlite3.connect(older)
    con.execute("CREATE TABLE matches (id INTEGER PRIMARY KEY)")
    con.commit()
    con.close()
    rc, out = _run(mod, ["--db", str(older)], capsys)
    assert rc == 2 and "cannot be read as the availability record's schema" in out and out.count("nothing read") == 1


@pytest.mark.parametrize("label", PREGAME + ["T+20"])
def test_370_the_labels_are_the_feeds_own(label):
    mod = _script()
    assert mod.PREGAME == tuple(PREGAME) and mod.EVENTUAL == "T+20"
    assert mod.GAME_OF.search(nl.game_url(7, nl.BOXSCORE if label == "T+20" else nl.LANDING)).group(1) == "7"



def _world2(tmp_path):
    """The cases the first world does not reach (#370's review):
    F: T+20 partial, asserting both sides.         G: T-120 failed, T-90 empty.
    H: two projections for the away side at T-60.  I: stored kickoffs 5h59m apart (read).
    J: stored kickoffs 6h apart (left out whole).  K: an observation at a label not the feed's (T-200).
    L: T-120 = T-0 = 5, T-90 .. T-15 missed.       M: its own NHL day, T+20 missed (the day shows 0/0).
    N: a slip across 10:00Z: the day is the newest observation's kickoff's."""
    st = Store(tmp_path / "copy2.db")
    full = [proj("away", 1), proj("home", 2)]
    base = datetime(2026, 11, 14, 0, 0)               # NHL day 2026-11-13
    F, G, H, I, J, K, L, M, N = range(2025020201, 2025020210)
    for label in PREGAME:
        st.poll(F, label, base, asserted=full)
    st.poll(F, "T+20", base, status="partial", asserted=[ev("away", 1), ev("home", 2)])
    for label in PREGAME:
        if label == "T-120":
            st.poll(G, label, base, status="failed")
        elif label == "T-90":
            st.poll(G, label, base, status="empty")
        else:
            st.poll(G, label, base, asserted=full)
    st.poll(G, "T+20", base, asserted=[ev("away", 1), ev("home", 2)])
    for label in PREGAME:
        st.poll(H, label, base, asserted=full + ([proj("away", 9)] if label == "T-60" else []))
    st.poll(H, "T+20", base, asserted=[ev("away", 1), ev("home", 2)])
    for gid, spread in ((I, timedelta(hours=5, minutes=59)), (J, timedelta(hours=6))):
        for label in PREGAME:
            k = base if PREGAME.index(label) < 3 else base + spread
            st.poll(gid, label, k, asserted=full)
        st.poll(gid, "T+20", base + spread, asserted=[ev("away", 1), ev("home", 2)])
    for label in PREGAME:
        st.poll(K, label, base, asserted=full)
    st.poll(K, "T-200", base, asserted=full)
    st.poll(K, "T+20", base, asserted=[ev("away", 1), ev("home", 2)])
    for label in PREGAME:
        if label in ("T-120", "T-0"):
            st.poll(L, label, base, asserted=[proj("away", 5), proj("home", 6)])
        else:
            st.poll(L, label, base, status="missed")
    st.poll(L, "T+20", base, asserted=[ev("away", 5), ev("home", 6)])
    kday = datetime(2026, 11, 16, 0, 0)               # NHL day 2026-11-15
    for label in PREGAME:
        st.poll(M, label, kday, asserted=full)
    st.poll(M, "T+20", kday, status="missed")
    early, late_k = datetime(2026, 11, 18, 9, 50), datetime(2026, 11, 18, 10, 20)   # NHL days 11-17 and 11-18
    for label in PREGAME:
        st.poll(N, label, early if PREGAME.index(label) < 3 else late_k, asserted=full)
    st.poll(N, "T+20", late_k, asserted=[ev("away", 1), ev("home", 2)])
    st.close()
    return tmp_path / "copy2.db", {"F": F, "G": G, "H": H, "I": I, "J": J, "K": K, "L": L, "M": M, "N": N}


def test_370_the_review_cases_each_read_as_ruled(tmp_path, capsys):
    mod = _script()
    copy, ids = _world2(tmp_path)
    rc, out = _run(mod, ["--db", str(copy)], capsys)
    assert rc == 0, out
    t = _tail(out)
    lines = out.splitlines()

    def side(gid, s):
        return next(x for x in lines if f" game {gid} {s}:" in x)

    # F: a partial T+20 is no eventual, though it asserts both sides
    assert "(T+20 partial)" in side(ids["F"], "away") and "projection: read · eventual: T+20 partial" in out
    # G: the failed and the empty landing keep their own reasons and status counts
    assert "T-120=(failed poll) T-90=(empty landing)" in side(ids["G"], "home")
    assert "projection: failed poll · eventual: read" in out and "projection: empty landing · eventual: read" in out
    assert "  T-120: complete 7, failed 1" in out and "   T-90: complete 6, empty 1, missed 1" in out
    # H: two projections for one side at one label are never chosen
    assert "T-60=(two projections)" in side(ids["H"], "away") and "T-60=2" in side(ids["H"], "home")
    # I read (5h59m), J left out whole (6h): the writer's six-hour series scope, both sides of the boundary
    assert side(ids["I"], "away")
    assert f"left out whole: game {ids['J']}: stored kickoffs 6:00:00 or more apart" in out
    assert t["series_left_out"] == [str(ids["J"])]
    # K: the T-200 row is named and in no count
    assert len(t["off_label"]) == 1 and "observations at a label not the feed's (in no count) 1" in out
    # L: the same playerId at T-120 and T-0 with six labels missed between is NOT stable from T-120: the run stops
    assert "first stable T-0 at the latest (a label with no projection before it)" in side(ids["L"], "away")
    assert t["first_stable_gap"]["T-0"] == 2
    # M: its day is shown although no side reached n
    assert any(x.startswith("  2026-11-15 ") and "0/0=n/a" in x for x in lines)
    # N: the day is the newest observation's kickoff's NHL day (10:20Z on 11-18), not the first's (09:50Z, 11-17)
    assert side(ids["N"], "away").startswith("  2026-11-18 ")
    # agreement per label over the games read: F (partial T+20), M (missed T+20) never reach n; G from T-60; H's away
    # not at T-60; I, K, L at T-120 and T-0 only, N
    assert t["per_label"]["T-120"] == [10, 10]       # H 2, I 2, K 2, L 2, N 2 (G failed)
    assert t["per_label"]["T-60"] == [9, 9]          # G 2, H home 1, I 2, K 2, N 2


def test_370_a_row_not_as_the_feed_writes_it_is_refused_not_a_traceback(tmp_path, capsys):
    mod = _script()
    copy, _ = _world(tmp_path)
    import sqlite3
    con = sqlite3.connect(copy)
    con.execute("DROP TRIGGER IF EXISTS trg_availability_assertions_update_guard")
    triggers = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")]
    for name in triggers:
        con.execute(f"DROP TRIGGER {name}")
    con.execute("UPDATE availability_assertions SET attrs = '[1, 2]' WHERE id = 1")
    con.commit()
    con.close()
    rc, out = _run(mod, ["--db", str(copy)], capsys)
    assert rc == 2 and "holds a row not as the feed writes it" in out and out.count("nothing read") == 1
