"""ARCHITECT 2026-10-03: dedupe --apply found 0 pairs on a table that showed 962 at 07:51. The read-only
receipt must explain a 0 rather than assume one: mergeable / SAME-id / 3+ clusters counted apart,
re-keyed-in-place rows counted, stale orphans named, duplicates in the export window flagged. Runs
against the throwaway test DB (conftest), opened read-only."""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Odds, Sport, Team

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ncaa_rekey_receipt as rr  # noqa: E402

SRC = "api_american_football"
NOW = datetime(2092, 10, 3, 16, 48)


@pytest.fixture(autouse=True, scope="module")
def _cleanup():
    yield
    with session_scope() as s:
        cids = [c.id for c in s.execute(select(Competition).where(Competition.code == "RR1")).scalars()]
        mids = [m.id for m in s.execute(select(Match).where(Match.competition_id.in_(cids))).scalars()]
        s.query(Odds).filter(Odds.match_id.in_(mids)).delete(synchronize_session=False)
        s.query(Match).filter(Match.id.in_(mids)).delete(synchronize_session=False)


def test_receipt_explains_a_zero_and_flags_window_duplicates(capsys):
    init_db()
    with session_scope() as s:
        c = Competition(sport=Sport.NFL, code="RR1", name="RR1", area="US", type="LEAGUE")
        names = ["Georgia Bulldogs", "Alabama Crimson Tide", "Pitt", "Virginia Tech", "Tulsa", "UNT", "WKU", "NMSU"]
        ts = [Team(sport=Sport.NFL, name=n, external_ids={SRC: f"rr{i}"}) for i, n in enumerate(names)]
        s.add(c)
        s.add_all(ts)
        s.flush()
        t = [x.id for x in ts]

        def m(h, a, sid, when, status=MatchStatus.SCHEDULED, prev=None):
            ext = {SRC: sid, **({f"{SRC}_prev": prev} if prev else {})}
            row = Match(sport=Sport.NFL, competition_id=c.id, season="2092", utc_date=when, status=status,
                        home_team_id=t[h], away_team_id=t[a], external_ids=ext)
            s.add(row)
            s.flush()
            return row.id

        ko = NOW + timedelta(hours=3)
        old = m(1, 0, "22612", ko)                         # Georgia @ Alabama: old id + new id -> mergeable
        new = m(1, 0, "23612", ko + timedelta(hours=1))
        s.add(Odds(match_id=new, bookmaker="b", market="ML", selection="HOME", price_decimal=1.5))
        m(3, 2, "24001", ko, prev=["22001"])               # re-keyed in place: one row, no twin
        m(5, 4, "23500", ko)                               # SAME id twice -> the dedupe refuses it
        m(5, 4, "23500", ko + timedelta(hours=2))
        m(7, 6, "22777", NOW - timedelta(days=1))          # stale old-id orphan (kickoff past, still SCHEDULED)
        db = os.environ["DATABASE_URL"][len("sqlite:///"):]
    assert rr.main(["--competition", "RR1", "--db", db, "--now", NOW.isoformat(), "--ids", str(old), str(new),
                    "--game", "Georgia@Alabama"]) == 0
    out = capsys.readouterr().out
    assert "re-keyed in place (carry api_american_football_prev) 1" in out
    assert "mergeable (different ids) 1 · SAME id 1 · missing id 0 · 3+ rows 0" in out
    assert "SCHEDULED with kickoff >6h past (stale; orphan candidates): 1 by id class {'22xxx': 1}" in out
    assert "rows 5 · distinct games (home, away, date) 3" in out and "DUPLICATES IN WINDOW" in out
    assert "6. Georgia@Alabama: 2 row(s)" in out and "sid 22612" in out and "odds 1" in out
    assert f"id {old} · Georgia Bulldogs @ Alabama Crimson Tide" in out


def test_audit_merges_names_rekeyed_rows_with_a_competing_same_pair_row(capsys):
    """PR #270 review: provenance audit of the applied merges — a re-keyed row with another same-pair row
    within 48h is named for review; isolated re-keyed rows stand."""
    init_db()
    with session_scope() as s:
        c = Competition(sport=Sport.NFL, code="RR2", name="RR2", area="US", type="LEAGUE")
        ts = [Team(sport=Sport.NFL, name=f"RR2 T{i}", external_ids={SRC: f"rr2{i}"}) for i in range(4)]
        s.add(c)
        s.add_all(ts)
        s.flush()
        t = [x.id for x in ts]
        log = [{"from": "1", "to": "2", "via": "orphan-merge", "at": "2092-10-03T20:00:00"}]
        for h, a, sid, dh, ext in ((1, 0, "2", 0, {f"{SRC}_prev": ["1"], f"{SRC}_rekeys": log}),
                                   (1, 0, "9", 30, {}),                       # competing twin still there
                                   (3, 2, "5", 0, {f"{SRC}_prev": ["4"]})):   # isolated: stands (pre-log)
            s.add(Match(sport=Sport.NFL, competition_id=c.id, season="2092", utc_date=NOW + timedelta(hours=dh),
                        status=MatchStatus.SCHEDULED, home_team_id=t[h], away_team_id=t[a],
                        external_ids={SRC: sid, **ext}))
        cid = c.id
        db = os.environ["DATABASE_URL"][len("sqlite:///"):]
    assert rr.main(["--competition", "RR2", "--db", db, "--now", NOW.isoformat(), "--audit-merges"]) == 0
    out = capsys.readouterr().out
    assert "7. merge provenance audit: 2 re-keyed row(s) · provenance log {'orphan-merge': 1}" in out
    assert "with another same-pair row within 48h: 1 (REVIEW these)" in out and "near:" in out and "sid 9" in out
    with session_scope() as s:
        s.query(Match).filter(Match.competition_id == cid).delete(synchronize_session=False)


def test_audit_zero_says_only_no_current_nearby_rows_and_reconstruction_catches_the_shift(tmp_path, capsys):
    """PR #270 review 2026-10-04 (boundary): a merge that moved the keeper's kickoff +40h leaves an
    unresolved twin 80h from the NEW kickoff but 40h from the OLD one. The current-table audit can only
    say "no current nearby rows found" (never "every merge stands"); --reconstruct-merges against the
    pre-apply backup names the kickoff shift, the twin near the PRE kickoff and the reference move."""
    import sqlite3

    init_db()
    with session_scope() as s:
        c = Competition(sport=Sport.NFL, code="RR3", name="RR3", area="US", type="LEAGUE")
        ts = [Team(sport=Sport.NFL, name=f"RR3 T{i}", external_ids={SRC: f"rr3{i}"}) for i in range(2)]
        s.add(c)
        s.add_all(ts)
        s.flush()
        t = [x.id for x in ts]

        def m(sid, dh):
            row = Match(sport=Sport.NFL, competition_id=c.id, season="2092", utc_date=NOW + timedelta(hours=dh),
                        status=MatchStatus.SCHEDULED, home_team_id=t[1], away_team_id=t[0], external_ids={SRC: sid})
            s.add(row)
            s.flush()
            return row.id

        twin = m("31", -40)                     # unresolved twin, 40h before the keeper's PRE kickoff
        keeper = m("30", 0)                     # stale old-id row (keeper: lower id than the live row)
        live = m("32", 40)                      # the live provider row, merged into the keeper
        s.add(Odds(match_id=live, bookmaker="b", market="ML", selection="HOME", price_decimal=1.8))
        cid = c.id
    db = os.environ["DATABASE_URL"][len("sqlite:///"):]
    pre = tmp_path / "pre_apply.backup"
    src, dst = sqlite3.connect(db), sqlite3.connect(pre)
    src.backup(dst)                             # the .backup API, into tmp (never data/)
    src.close()
    dst.close()
    with session_scope() as s:                  # what the old algorithm's apply did
        k, n = s.get(Match, keeper), s.get(Match, live)
        s.query(Odds).filter(Odds.match_id == live).update({"match_id": keeper}, synchronize_session=False)
        k.utc_date = n.utc_date
        k.external_ids = {SRC: "32", f"{SRC}_prev": ["30"],
                          f"{SRC}_rekeys": [{"from": "30", "to": "32", "via": "orphan-merge", "at": "2092-10-03T20:00:00"}]}
        s.delete(n)
    assert rr.main(["--competition", "RR3", "--db", db, "--now", NOW.isoformat(), "--audit-merges"]) == 0
    out = capsys.readouterr().out
    assert "with another same-pair row within 48h: 0 (no current nearby rows found)" in out
    assert "every merge stands" not in out
    plan = tmp_path / "plan.txt"
    plan.write_text(f"  [merge] id {keeper} sid 30 {NOW.isoformat()} home {t[1]} away {t[0]} STALE "
                    f"{{'twin': {live}, 'twin_sid': '32', 'keeper': {keeper}}}\n")
    assert rr.main(["--competition", "RR3", "--db", db, "--now", NOW.isoformat(), "--reconstruct-merges",
                    "--backup", str(pre), "--plan", str(plan), "--expect", "1"]) == 0
    out = capsys.readouterr().out
    assert "orphan merges in the provenance log: 1 · reported 1" in out
    assert f"merged row id {live} sid 32" in out
    assert "SHIFTED 1 day, 16:00:00" in out
    assert f"same-pair row near the pre kickoff (now): id {twin} sid 31" in out
    assert "odds: keeper 0→1, merged 1→0 (every row identity and destination verified)" in out
    assert "in the plan but not in the log none" in out
    assert "RECONSTRUCTION: merges 1/1" in out and "REVIEW" in out
    assert str(tmp_path) not in out                      # sanitised: the backup is named, not its path
    assert rr.main(["--competition", "RR3", "--db", db, "--reconstruct-merges"]) == 2   # no --backup: refused
    with session_scope() as s:
        mids = [x.id for x in s.query(Match).filter(Match.competition_id == cid)]
        s.query(Odds).filter(Odds.match_id.in_(mids)).delete(synchronize_session=False)
        s.query(Match).filter(Match.competition_id == cid).delete(synchronize_session=False)


def _clean_merge(tmp_path, code):
    """A clean orphan merge (keeper keeps its kickoff, odds row moved, nothing near): the baseline that
    reconstructs ACCOUNTED. Returns (db, backup, plan text, keeper id, merged id, cid, team ids)."""
    import sqlite3

    init_db()
    with session_scope() as s:
        c = Competition(sport=Sport.NFL, code=code, name=code, area="US", type="LEAGUE")
        ts = [Team(sport=Sport.NFL, name=f"{code} T{i}", external_ids={SRC: f"{code.lower()}{i}"}) for i in range(2)]
        s.add(c)
        s.add_all(ts)
        s.flush()
        t = [x.id for x in ts]
        rows = []
        for sid, dh in (("40", 0), ("41", 2)):
            m = Match(sport=Sport.NFL, competition_id=c.id, season="2092", utc_date=NOW + timedelta(hours=dh),
                      status=MatchStatus.SCHEDULED, home_team_id=t[1], away_team_id=t[0], external_ids={SRC: sid})
            s.add(m)
            s.flush()
            rows.append(m.id)
        keeper, live = rows
        s.add(Odds(match_id=live, bookmaker="b", market="ML", selection="HOME", price_decimal=1.8))
        cid = c.id
    db = os.environ["DATABASE_URL"][len("sqlite:///"):]
    pre = tmp_path / f"{code}.backup"
    src, dst = sqlite3.connect(db), sqlite3.connect(pre)
    src.backup(dst)
    src.close()
    dst.close()
    with session_scope() as s:
        k = s.get(Match, keeper)
        s.query(Odds).filter(Odds.match_id == live).update({"match_id": keeper}, synchronize_session=False)
        k.external_ids = {SRC: "40", f"{SRC}_prev": ["41"],
                          f"{SRC}_rekeys": [{"from": "41", "to": "40", "via": "orphan-merge", "at": "2092-10-03T20:00:00"}]}
        s.delete(s.get(Match, live))
    plan = (f"  [merge] id {keeper} sid 40 {NOW.isoformat()} home {t[1]} away {t[0]} STALE "
            f"{{'twin': {live}, 'twin_sid': '41', 'keeper': {keeper}}}\n")
    return db, pre, plan, keeper, live, cid


def _drop(cid):
    with session_scope() as s:
        mids = [x.id for x in s.query(Match).filter(Match.competition_id == cid)]
        s.query(Odds).filter(Odds.match_id.in_(mids)).delete(synchronize_session=False)
        s.query(Match).filter(Match.competition_id == cid).delete(synchronize_session=False)


def _reconstruct(code, db, pre, plan_path, capsys):
    assert rr.main(["--competition", code, "--db", db, "--now", NOW.isoformat(), "--reconstruct-merges",
                    "--backup", str(pre), "--plan", str(plan_path), "--expect", "1"]) == 0
    return capsys.readouterr().out


def test_plan_naming_a_different_merged_row_is_review(tmp_path, capsys):
    """#277 review (reproduced on 70acdbbf): the cross-check compared keeper ids only, so a plan naming a
    different merged row reported no mismatch. Keeper AND merged ids and both provider ids are compared."""
    db, pre, plan, keeper, live, cid = _clean_merge(tmp_path, "RR4")
    good = tmp_path / "good.txt"
    good.write_text(plan)
    out = _reconstruct("RR4", db, pre, good, capsys)
    assert "plan: keeper + merged row ids and both provider ids match" in out and "· ACCOUNTED" in out
    bad = tmp_path / "bad.txt"
    bad.write_text(plan.replace(f"'twin': {live}", f"'twin': {live + 999}"))
    out = _reconstruct("RR4", db, pre, bad, capsys)
    assert "⚠ plan disagrees" in out and "· REVIEW" in out and "ACCOUNTED" not in out
    sid_bad = tmp_path / "sid.txt"
    sid_bad.write_text(plan.replace("'twin_sid': '41'", "'twin_sid': '49'"))
    out = _reconstruct("RR4", db, pre, sid_bad, capsys)
    assert "⚠ plan disagrees" in out and "· REVIEW" in out
    _drop(cid)


def test_replaced_reference_row_is_review_even_with_equal_counts(tmp_path, capsys):
    """#277 review (reproduced on 70acdbbf): replacing the original odds row with a different row kept the
    counts and returned ACCOUNTED. Each pre row's identity (rowid + content) and destination is verified."""
    db, pre, plan, keeper, live, cid = _clean_merge(tmp_path, "RR5")
    p = tmp_path / "plan.txt"
    p.write_text(plan)
    with session_scope() as s:                          # same count on the keeper, a DIFFERENT row
        s.query(Odds).filter(Odds.match_id == keeper).delete(synchronize_session=False)
        s.add(Odds(match_id=keeper, bookmaker="b", market="ML", selection="HOME", price_decimal=1.8))
    out = _reconstruct("RR5", db, pre, p, capsys)
    # SQLite may hand the replacement the freed rowid: then the CONTENT differs; else the old row is gone
    assert "odds: keeper 0→1, merged 1→0 ⚠" in out and ("content changed" in out or "gone" in out)
    assert "· REVIEW" in out and "ACCOUNTED" not in out
    _drop(cid)


def test_post_backup_rows_repointed_keyed_rows_and_a_placeholder_kickoff_are_accounted(tmp_path, capsys):
    """ARCHITECT 2026-10-05 (#277 reconstruction 30/30, RULED ACCOUNTED): 'reference move not accounted' ×11
    were rows created after the backup (post-backup syncs) + match_id re-pointed rows; 'keeper kickoff
    shifted' ×30 were placeholder 04:00Z → real kickoffs. A clean merge carrying all three reads ACCOUNTED;
    a replaced row still reads REVIEW (the test above)."""
    import sqlite3

    from src.db.schema import MatchNeutralDerived
    init_db()
    place = NOW.replace(hour=4, minute=0, second=0, microsecond=0)
    with session_scope() as s:
        c = Competition(sport=Sport.NFL, code="RR6", name="RR6", area="US", type="LEAGUE")
        ts = [Team(sport=Sport.NFL, name=f"RR6 T{i}", external_ids={SRC: f"rr6{i}"}) for i in range(2)]
        s.add(c)
        s.add_all(ts)
        s.flush()
        t = [x.id for x in ts]
        rows = []
        for sid, when in (("60", place), ("61", place + timedelta(hours=15, minutes=30))):
            m = Match(sport=Sport.NFL, competition_id=c.id, season="2092", utc_date=when,
                      status=MatchStatus.SCHEDULED, home_team_id=t[1], away_team_id=t[0], external_ids={SRC: sid})
            s.add(m)
            s.flush()
            rows.append(m.id)
        keeper, live = rows
        s.add(Odds(match_id=live, bookmaker="b", market="ML", selection="HOME", price_decimal=1.8))
        s.add(MatchNeutralDerived(match_id=live, neutral_derived=False, rule="r"))   # keyed BY match_id
        cid = c.id
    db = os.environ["DATABASE_URL"][len("sqlite:///"):]
    pre = tmp_path / "RR6.backup"
    src, dst = sqlite3.connect(db), sqlite3.connect(pre)
    src.backup(dst)
    src.close()
    dst.close()
    with session_scope() as s:                       # the merge: take the live row's kickoff, re-point refs
        k, n = s.get(Match, keeper), s.get(Match, live)
        k.utc_date = n.utc_date
        s.query(Odds).filter(Odds.match_id == live).update({"match_id": keeper}, synchronize_session=False)
        s.query(MatchNeutralDerived).filter(MatchNeutralDerived.match_id == live).update(
            {"match_id": keeper}, synchronize_session=False)
        k.external_ids = {SRC: "60", f"{SRC}_prev": ["61"],
                          f"{SRC}_rekeys": [{"from": "61", "to": "60", "via": "orphan-merge", "at": "2092-10-03T20:00:00"}]}
        s.delete(n)
    with session_scope() as s:                       # a later sync adds a row (rowid above the backup's max)
        s.add(Odds(match_id=keeper, bookmaker="b2", market="ML", selection="AWAY", price_decimal=2.1))
    plan = tmp_path / "plan.txt"
    plan.write_text(f"  [merge] id {keeper} sid 60 {place.isoformat()} home {t[1]} away {t[0]} STALE "
                    f"{{'twin': {live}, 'twin_sid': '61', 'keeper': {keeper}}}\n")
    assert rr.main(["--competition", "RR6", "--db", db, "--now", NOW.isoformat(), "--reconstruct-merges",
                    "--backup", str(pre), "--plan", str(plan), "--expect", "1"]) == 0
    out = capsys.readouterr().out
    assert "placeholder 04:00Z → real kickoff" in out
    assert "'created after the backup': 1" in out and "'re-pointed (rowid follows match_id)': 1" in out
    assert "flags none" in out and out.rstrip().endswith("ACCOUNTED")
    with session_scope() as s:
        mids = [x.id for x in s.query(Match).filter(Match.competition_id == cid)]
        s.query(Odds).filter(Odds.match_id.in_(mids)).delete(synchronize_session=False)
        s.query(MatchNeutralDerived).filter(MatchNeutralDerived.match_id.in_(mids)).delete(synchronize_session=False)
        s.query(Match).filter(Match.competition_id == cid).delete(synchronize_session=False)


def test_review_boundaries_placeholder_destination_and_empty_backup_table():
    """#279 review (Codex): a 04:00Z → next-day 04:00Z move is a date change, not a placeholder resolved;
    an EMPTY backup table's max rowid is 0 (every current row post-backup), a missing one None."""
    import sqlite3

    p = datetime(2092, 10, 5, 4, 0)
    assert rr.placeholder_resolved(p, p.replace(hour=19, minute=30))
    assert not rr.placeholder_resolved(p, p + timedelta(days=1))           # placeholder → placeholder
    assert not rr.placeholder_resolved(p, p - timedelta(days=1))
    assert not rr.placeholder_resolved(p, p + timedelta(hours=30))         # beyond 24h
    assert not rr.placeholder_resolved(p.replace(hour=17), p.replace(hour=19))   # not a placeholder origin
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE odds (id INTEGER PRIMARY KEY, match_id INTEGER)")
    assert rr.max_rowid(con, "odds") == 0 and rr.max_rowid(con, "nope") is None


def test_post_backup_row_dangling_on_the_merged_id_is_review(tmp_path, capsys):
    """#279 review (Codex, post-merge): a row created after the backup is accounted only when it points at
    the KEEPER. Without FK enforcement a later row can still dangle on the merged-away id; it reads REVIEW."""
    db, pre, plan, keeper, live, cid = _clean_merge(tmp_path, "RR7")
    p = tmp_path / "plan.txt"
    p.write_text(plan)
    with session_scope() as s:                          # a later sync writes onto the merged-away id
        s.add(Odds(match_id=live, bookmaker="b2", market="ML", selection="AWAY", price_decimal=2.1))
    out = _reconstruct("RR7", db, pre, p, capsys)
    assert f"created after the backup still on merged match {live}" in out
    assert "merged 1→1 ⚠" in out and "· REVIEW" in out and "ACCOUNTED" not in out
    with session_scope() as s:
        s.query(Odds).filter(Odds.match_id == live).delete(synchronize_session=False)
    _drop(cid)
