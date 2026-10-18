"""THE SLATE RUN (ARCHITECT 2026-10-18, addendum 126 items 1-2, #590), on the closing-run test frame
(tests/test_closing_runs.py: a SCRATCH schedule in a throwaway DB under tmp_path, every step, page, push and
notification faked, the network blocked; the fixture's slate stage is turned on here with box.slate_on()).

Item 2(e), the spec's own test: "a synthetic day with one family's games at 09:30 and 13:00 ET: the slate is due at
07:00, runs once, writes the slate file with desk blocks, pages once; the closing groups still run at 08:55 and 12:25;
a second tick does not re-run the slate; a failed export pages the RUN BY HAND text and names the block." Then the
edges #590 names: three failed attempts and no fourth, a first tick after 06:00 when the due time was earlier, a tick
at 05:59, a day with no games, a refused family, and the closing receipt readers beside the slate's lines."""
import contextlib
import fnmatch
import hashlib
import inspect
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.test_closing_runs import (  # noqa: F401  (box is a fixture)
    MACHINE, box, c, dp, hold_lock, make_db, mc, receipts, row, runs)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))
import sp_receipts  # noqa: E402

UTC = timezone.utc
D18 = date(2026, 10, 18)                                   # a Sunday (EDT, UTC-4)
BASE = datetime(2026, 10, 18, 11, 0, tzinfo=UTC)           # 07:00 ET
NFL_FILE = "exports/nfl_predictions_2026-10-18.json"
BLOCK = "block_1018_nfl_slate.txt"
# (match_id, competition, minutes from BASE, status, home): NFL at 09:30 ET (London) and 13:00 ET; MLB at 13:05 ET
DAY = [(601, "NFL", 150, "SCHEDULED", "London"), (602, "NFL", 360, "SCHEDULED", "Buffalo"),
       (701, "MLB", 365, "SCHEDULED", "Underhill")]
SLATE_STEPS = [
    "python cli.py sync-matches --competition NFL --season 2026 --date-from 2026-10-18 --date-to 2026-10-18 "
    "--match-ids 601,602",
    "python cli.py sync-injuries --competition NFL --season 2026 --match-ids 601,602 --strict",
    "python cli.py sync-odds-football --match-ids 601,602",
    "python cli.py sync-kalshi-nfl",
    "python cli.py predict-nfl",
    f"python cli.py export-nfl-predictions --desk --out {NFL_FILE}"]
PAGE = f"SLATE NFL 2026-10-18: 2 rows · PLAY 1 · PASS 1 · {NFL_FILE}\n{MACHINE}"


def et(hh, mm, day=D18):
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=mc.NY).astimezone(UTC)


def nfl_rows(now=BASE):
    k = {"comp": "NFL", "series": "KXNFLGAME", "now": now}
    return [row(601, "London", 0.62, fair_h=0.55, bid=0.54, ask=0.55, minutes=150, **k),       # PLAY
            row(602, "Buffalo", 0.52, fair_h=0.515, bid=0.51, ask=0.52, minutes=360, **k)]     # PASS


def the_day(box, monkeypatch, games=DAY, slate=True):
    """Sunday 2026-10-18 in a throwaway DB, its exports as the export steps write them, the slate stage on."""
    db = box.tmp / "day18.db"
    make_db(db, games, now=BASE)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    box.db = db
    box.docs["NFL"] = dp.annotate({"sport": "nfl", "predictions": nfl_rows()}, now=BASE)
    box.docs["MLB"] = dp.annotate({"sport": "mlb", "predictions": [
        row(701, "Underhill", 0.52, fair_h=0.51, bid=0.50, ask=0.51, minutes=365, now=BASE)]}, now=BASE)
    if slate:
        box.slate_on()


def slates(fam="NFL"):
    return [r for r in receipts() if r["kind"] == "slate" and r["family"] == fam]


def misses(fam="NFL"):
    return [r for r in receipts() if r["kind"] == "slate_miss" and r["family"] == fam]


def slate_pages(box, fam="NFL"):
    return [p for p in box.pages if p["title"] == f"{fam} slate 2026-10-18"]


def tick(t, fams=("NFL",)):
    return mc.watch(now=t, families=fams)


# ============================================================================== the spec's test, item 2(e) ==

@pytest.mark.parametrize("slate", [True, False], ids=["slate-on", "slate-off"])
def test_the_slate_day_and_the_closings_beside_it_unchanged(box, monkeypatch, slate):
    """Every minute from 05:55 to 13:05 ET: the slate is due at 07:00 (09:30 - 150 minutes), runs once, writes the
    slate file with desk blocks and pages once, with the exact text; no later tick re-runs it. The closing groups run
    at 08:55 and 12:25 ET, each covering its own game, with the same steps and the same files whether the slate stage
    is on or off (the pin: the closings are unchanged)."""
    the_day(box, monkeypatch, slate=slate)
    t = et(5, 55)
    while t <= et(13, 5):
        assert tick(t) == 0, t
        t += timedelta(minutes=1)
    if slate:
        (s,) = slates()
        assert (s["queued_at"], s["due"], s["date"], s["attempt"], s["exit"]) == (
            "2026-10-18T11:00:00Z", "2026-10-18T11:00:00Z", "2026-10-18", 1, 0)
        assert (s["file"], s["rows"], s["calls"], s["late_minutes"], s["late"]) == (
            NFL_FILE, 2, {"PLAY": 1, "PASS": 1}, 0, False)
        assert [x["command"] for x in s["steps"]] == SLATE_STEPS and s["push"]["exit"] == 0
        assert [x["match_id"] for x in s["covers"]] == [601, 602] and s["page"]["phone"]["accepted"] is True
        f = box.repo / NFL_FILE
        doc = json.loads(f.read_text())
        assert doc["desk_meta"] and [p["desk"]["call"] for p in doc["predictions"]] == ["PLAY", "PASS"]
        assert slate_pages(box) == [{"title": "NFL slate 2026-10-18", "body": PAGE, "priority": "default"}]
        assert box.notes[0] == PAGE                                   # the screen: the same page
        # ONE CLOSING, ONE PAGE, ONE FILE: no closing writes, replaces or moves the slate file
        assert hashlib.sha256(f.read_bytes()).hexdigest() == s["export_written"]["sha256"]
        assert box.pushes == ["slate", "closing", "closing"]
    else:
        assert slates() == [] and not (box.repo / NFL_FILE).exists() and box.pushes == ["closing", "closing"]
    got = [(r["queued_at"], r["start"], [x["match_id"] for x in r["covers"]], r["exit"],
            [x["command"].replace(r["run_id"], "RUN") for x in r["steps"]], r["closing_file"]["file"])
           for r in runs("NFL")]
    assert got == [
        ("2026-10-18T12:55:00Z", "2026-10-18T13:30:00Z", [601], 0, closing_steps(601), CLOSING_FILE.format("1330")),
        ("2026-10-18T16:25:00Z", "2026-10-18T17:00:00Z", [602], 0, closing_steps(602), CLOSING_FILE.format("1700"))]
    assert box.lock_seen and not any(box.lock_seen)                   # every step, slate and closing, under the lock
    assert [p["title"] for p in box.pages if "closing" in p["title"]] == ["NFL closing 09:30 ET",
                                                                          "NFL closing 13:00 ET"]


CLOSING_FILE = "exports/closing_NFL_2026-10-18T{}Z.json"


def closing_steps(mid):
    return ["python cli.py sync-matches --competition NFL --season 2026 --date-from 2026-10-18 --date-to 2026-10-18 "
            f"--match-ids {mid}",
            f"python cli.py sync-injuries --competition NFL --season 2026 --match-ids {mid} --strict",
            f"python cli.py sync-odds-football --match-ids {mid}", "python cli.py sync-kalshi-nfl",
            "python cli.py predict-nfl",
            "python cli.py export-nfl-predictions --desk --out logs/RUN.nfl_predictions_2026-10-18.json"]


def test_a_second_tick_does_not_rerun_the_slate(box, monkeypatch):
    the_day(box, monkeypatch)
    assert tick(et(6, 59)) == 0 and slates() == [] and box.steps == []          # before 07:00: nothing
    assert tick(et(7, 0)) == 0 and len(slates()) == 1 and len(box.steps) == 6
    for m in (1, 2, 30):
        assert tick(et(7, m)) == 0
    assert len(slates()) == 1 and len(box.steps) == 6 and len(slate_pages(box)) == 1


def test_a_failed_export_pages_run_by_hand_and_three_attempts_then_no_fourth(box, monkeypatch):
    """A failed step pages "SLATE NFL FAILED: <step> — RUN BY HAND: block …" the way a closing failure pages (its
    attempt out of three, the third saying no further attempt runs, the machine's line last); three attempts, then
    the watch runs no fourth that day."""
    the_day(box, monkeypatch)
    box.fail_cmd["export-nfl-predictions"] = (1, ["boom"])
    for m in range(3):
        assert tick(et(7, m)) == mc.NOTIFIED
    assert tick(et(7, 3)) == 0                                                   # no fourth
    s = slates()
    assert [(r["attempt"], r["exit"], r["failed"]) for r in s] == [(1, 1, "step 6"), (2, 1, "step 6"), (3, 1, "step 6")]
    cmd = f"python cli.py export-nfl-predictions --desk --out {NFL_FILE}"
    assert s[0]["step"] == cmd and s[0]["steps"][-1]["tail"] == ["boom"]
    head = f"SLATE NFL FAILED: {cmd} — RUN BY HAND: {BLOCK}"
    assert box.notes == [f"{head} · attempt 1/3\n{MACHINE}", f"{head} · attempt 2/3\n{MACHINE}",
                         f"{head} · attempt 3/3 · no further attempt will run today\n{MACHINE}"]
    assert [p["title"] for p in box.pages] == ["NFL slate"] * 3 and {p["priority"] for p in box.pages} == {"high"}
    assert s[0]["failure_notification"]["channel"] == "card+screen"
    assert box.pushes == [] and slate_pages(box) == [] and not (box.repo / NFL_FILE).exists()
    assert mc.slate_state("NFL", "2026-10-18") == {"success": False, "attempts": 3}


def test_a_failed_first_attempt_then_a_success_on_the_next_tick(box, monkeypatch):
    the_day(box, monkeypatch)
    box.fail_cmd["sync-odds-football"] = (1, ["provider 500"])
    assert tick(et(7, 0)) == mc.NOTIFIED
    assert box.notes[-1].startswith("SLATE NFL FAILED: python cli.py sync-odds-football --match-ids 601,602 — RUN BY "
                                    f"HAND: {BLOCK} · attempt 1/3")
    box.fail_cmd.clear()
    assert tick(et(7, 5)) == 0
    assert [(r["attempt"], r["exit"]) for r in slates()] == [(1, 1), (2, 0)]
    # late is judged on the day's first attempt (07:00, on time): a retry five minutes on is not the laptop asleep
    assert slate_pages(box)[-1]["body"] == PAGE and slates()[-1]["late"] is False
    assert tick(et(7, 6)) == 0 and len(slates()) == 2                            # a success ends the day


@pytest.mark.parametrize("first, late", [((6, 0), None), ((6, 40), 40)], ids=["at-06:00", "laptop-woke-06:40"])
def test_a_due_time_before_06_00_is_06_00_and_a_late_first_tick_says_so(box, monkeypatch, first, late):
    """A first kickoff at 08:00 ET: 08:00 - 150 minutes is 05:30, so the slate is due at the first tick after 06:00
    ET. A tick at 05:59 does nothing. A first tick more than one cadence after the due time (the laptop asleep) runs it
    and the page says it was late, with the minutes."""
    the_day(box, monkeypatch, games=[(603, "NFL", 60, "SCHEDULED", "Early")])
    box.docs["NFL"] = dp.annotate({"sport": "nfl", "predictions": [
        row(603, "Early", 0.52, fair_h=0.515, bid=0.51, ask=0.52, minutes=60, comp="NFL", series="KXNFLGAME",
            now=BASE)]}, now=BASE)
    assert tick(et(5, 59)) == 0 and receipts() == [] and box.steps == box.pages == box.notes == []
    assert tick(et(*first)) == 0
    (s,) = slates()
    assert s["due"] == "2026-10-18T10:00:00Z" and s["late"] is bool(late) and s["late_minutes"] == (late or 0)
    lines = [f"SLATE NFL 2026-10-18: 1 rows · PLAY 0 · PASS 1 · {NFL_FILE}", MACHINE]
    if late:
        lines.insert(1, "LATE 40 min: due 06:00 ET, run 06:40 ET")
    assert slate_pages(box)[0]["body"].splitlines() == lines


def test_the_due_time():
    assert mc.slate_due(et(9, 30), D18) == et(7, 0)                              # first kickoff - 150 minutes
    assert mc.slate_due(et(8, 0), D18) == et(6, 0) and mc.slate_due(et(7, 10), D18) == et(6, 0)   # 06:00 ET floor
    assert mc.WATCH_CADENCE_S == 60 and mc.SLATE_LEAD_MIN == 150 and mc.SLATE_NOT_BEFORE_ET == (6, 0)


def test_a_tick_one_cadence_after_the_due_time_is_on_time(box, monkeypatch):
    """Late is a first tick more than the watch's cadence (60 s) after the due time: the tick at 07:01 for 07:00 is
    the normal cadence, on time (the minutes recorded, no LATE line); two minutes is late (the MLB test below)."""
    the_day(box, monkeypatch)
    assert tick(et(7, 1)) == 0
    (s,) = slates()
    assert (s["late"], s["late_minutes"]) == (False, 1) and slate_pages(box)[0]["body"] == PAGE


def test_a_day_with_no_games_does_nothing(box, monkeypatch):
    the_day(box, monkeypatch, games=[(604, "NFL", 24 * 60 + 600, "SCHEDULED", "Monday")])    # the next day only
    for t in (et(6, 0), et(7, 0), et(12, 0)):
        assert tick(t) == 0
    assert receipts() == [] and box.steps == box.pages == box.notes == box.pushes == []
    assert mc.day_games("NFL", D18) == [] and [g["match_id"] for g in mc.day_games("NFL", date(2026, 10, 19))] == [604]


def test_a_refused_family_writes_no_slate_and_pages_nothing(box, monkeypatch):
    """The family refusal applies to the slate as to the closing (SP_SKIP_FAMILIES; MLB on the host): no step, no
    file, no page, no notice; receipted once for the day and reason."""
    the_day(box, monkeypatch)
    monkeypatch.setenv("SP_SKIP_FAMILIES", "NFL")
    assert tick(et(7, 0)) == 2 and tick(et(7, 1)) == 2
    (s,) = slates()
    assert s["refused"] == "SP_SKIP_FAMILIES names NFL here" and s["exit"] == 2 and "failure_notification" not in s
    assert box.steps == box.pages == box.notes == box.pushes == [] and not (box.repo / NFL_FILE).exists()
    assert mc.slate_state("NFL", "2026-10-18") == {"success": False, "attempts": 0}   # a refusal is no attempt
    monkeypatch.setenv("SP_SKIP_FAMILIES", "MLB")
    assert tick(et(10, 35), ("MLB",)) == 2
    assert slates("MLB")[0]["refused"].startswith("laptop only") and box.pages == [] and box.feed_calls == 0


def test_another_refusal_is_notified_once_for_the_day_and_reason(box, monkeypatch):
    the_day(box, monkeypatch)
    monkeypatch.delenv("SP_EXPORTS_MIRROR_REMOTE")
    assert tick(et(7, 0)) == 2 and tick(et(7, 1)) == 2
    (s,) = slates()
    assert s["refused"].startswith("SP_EXPORTS_MIRROR_REMOTE is not set") and box.steps == []
    assert box.notes == [f"SLATE NFL 2026-10-18 REFUSED: {s['refused']} — RUN BY HAND: {BLOCK}\n{MACHINE}"]


# ====================================================================================== the closing readers ==

def test_the_closing_receipt_readers_ignore_the_slate_lines(box, monkeypatch):
    """A slate success (kind slate, exit 0, covering 601 and 602) and a slate miss beside it: closing_state,
    _attempts, covered_ids, unpaged_called_off and due() read kind closing only, so the 09:30 closing is still due at
    08:55 and has no attempt; last_calls reads the slate FILE as the morning file (an export no closing run wrote)."""
    the_day(box, monkeypatch)
    assert tick(et(7, 0)) == 0 and slates()[0]["exit"] == 0
    mc.record_slate_miss("NFL", D18, "the chain lock was held")
    assert {r["kind"] for r in receipts()} == {"slate", "slate_miss"}
    start = "2026-10-18T13:30:00Z"
    assert mc.closing_state("NFL", start) == {"success": False, "attempts": 0, "misses": 0}
    assert mc._attempts("NFL") == [] and mc.covered_ids("NFL") == set()
    assert mc.unpaged_called_off("NFL", et(8, 55)) == []
    d = mc.due("NFL", et(8, 55))
    assert [(g["start"], [x["match_id"] for x in g["games"]]) for g in d["due"]] == [(et(9, 30), [601])]
    lc = mc.last_calls("NFL", et(8, 55))
    assert {k: (v["call"], v["source"]) for k, v in lc.items()} == {
        601: ("PLAY London 1u", "nfl_predictions_2026-10-18.json"), 602: ("PASS", "nfl_predictions_2026-10-18.json")}


def test_the_receipts_table_shows_the_slate_lines():
    ok = {"kind": "slate", "family": "NFL", "date": "2026-10-18", "file": NFL_FILE, "rows": 12,
          "calls": {"PLAY": 1, "PASS": 11}, "exit": 0, "late": True, "late_minutes": 47}
    assert sp_receipts.key_line(ok) == f"NFL 2026-10-18 slate {NFL_FILE}: 12 rows, PLAY 1, PASS 11; LATE 47 min"
    assert not sp_receipts.failed(ok)
    bad = {**ok, "exit": 1, "failed": "step 6", "attempt": 2}
    assert sp_receipts.key_line(bad) == "NFL 2026-10-18 slate attempt 2 FAILED: step 6" and sp_receipts.failed(bad)
    miss = {"kind": "slate_miss", "family": "MLB", "date": "2026-10-18", "reason": "feed unreachable"}
    assert sp_receipts.key_line(miss) == "MLB 2026-10-18 slate MISSED: feed unreachable" and sp_receipts.failed(miss)
    held = {"kind": "slate", "family": "MLB", "date": "2026-10-18", "exit": 0,
            "held": "closing NFL 13:00 ET (T-35 12:25 ET) is inside the 15-minute guard"}
    assert sp_receipts.key_line(held) == ("MLB 2026-10-18 slate held: closing NFL 13:00 ET (T-35 12:25 ET) is inside "
                                          "the 15-minute guard") and not sp_receipts.failed(held)


# ============================================================================================ the run's edges ==

def test_mlb_feed_unreachable_is_one_miss_then_the_slate_runs_when_it_answers(box, monkeypatch):
    """A6, as the watch checks it before an MLB closing: the feed unreachable is a miss, receipted and notified once
    for the day, not an attempt; the watch keeps trying silently and runs the slate when the feed answers. Not late
    (item 2(d), the laptop asleep): the watch ticked at 10:35, the due time; the miss's receipt carries that tick."""
    the_day(box, monkeypatch)
    box.feed = (False, "URLError")
    assert tick(et(10, 34), ("MLB",)) == 0 and box.feed_calls == 0               # 13:05 - 150 = 10:35: not yet
    assert tick(et(10, 35), ("MLB",)) == mc.NOTIFIED and tick(et(10, 36), ("MLB",)) == mc.NOTIFIED
    assert [m["reason"] for m in misses("MLB")] == ["feed unreachable"] and slates("MLB") == [] and box.steps == []
    assert (misses("MLB")[0]["queued_at"], misses("MLB")[0]["due"]) == ("2026-10-18T14:35:00Z", "2026-10-18T14:35:00Z")
    assert box.notes == ["SLATE MLB 2026-10-18 MISSED: MLB feed unreachable: VPN on, Tailscale off — RUN BY HAND: "
                         f"block_1018_mlb_slate.txt · the watch keeps trying\n{MACHINE}"]
    box.feed = (True, "HTTP 200")
    assert tick(et(10, 37), ("MLB",)) == 0
    (s,) = slates("MLB")
    assert s["exit"] == 0 and s["attempt"] == 1 and len(s["steps"]) == 10
    assert s["steps"][0]["command"] == ("python cli.py sync-matches --competition MLB --season 2026 --date-from "
                                        "2026-10-18 --date-to 2026-10-18 --match-ids 701")
    assert s["steps"][-1]["command"] == ("python cli.py export-predictions --sport mlb --competition MLB --date "
                                         "2026-10-18 --desk --out exports/mlb_MLB_2026-10-18.json")
    assert (s["late"], s["late_minutes"]) == (False, 0)                         # first tick 10:35: on time
    assert slate_pages(box, "MLB")[0]["body"].splitlines() == [
        "SLATE MLB 2026-10-18: 1 rows · PLAY 0 · PASS 1 · exports/mlb_MLB_2026-10-18.json", MACHINE]


def test_a_file_missing_a_game_of_the_day_fails_and_is_not_pushed(box, monkeypatch):
    the_day(box, monkeypatch)
    box.docs["NFL"]["predictions"] = box.docs["NFL"]["predictions"][:1]          # 602 missing
    assert tick(et(7, 0)) == mc.NOTIFIED
    (s,) = slates()
    assert s["failed"] == "missing from export" and [m["match_id"] for m in s["missing"]] == [602]
    assert box.notes == [f"SLATE NFL FAILED: missing from export ({NFL_FILE}): match 602 — RUN BY HAND: {BLOCK} · "
                         f"attempt 1/3\n{MACHINE}"]
    assert box.pushes == [] and slate_pages(box) == []
    # the file the export wrote stays in exports/ (as a prematch chain's): this run pushed nothing, the machine's next
    # push carries it (docs/CLI.md)
    assert [p["match_id"] for p in json.loads((box.repo / NFL_FILE).read_text())["predictions"]] == [601]


def test_a_file_without_desk_calls_fails(box, monkeypatch):
    the_day(box, monkeypatch)
    box.docs["NFL"] = {"sport": "nfl", "predictions": nfl_rows()}                # exported without --desk
    assert tick(et(7, 0)) == mc.NOTIFIED
    assert slates()[0]["failed"] == "export carries no desk calls"
    assert box.notes[0].startswith(f"SLATE NFL FAILED: {NFL_FILE} carries no desk calls — RUN BY HAND: {BLOCK}")


def test_a_failed_push_fails_the_attempt_and_pages_no_slate(box, monkeypatch):
    the_day(box, monkeypatch)
    monkeypatch.setattr(mc, "push_mirror", lambda label="closing": box.pushes.append(label) or {"exit": 1,
                                                                                            "tail": ["rejected"]})
    assert tick(et(7, 0)) == mc.NOTIFIED
    assert slates()[0]["failed"] == "push" and box.pushes == ["slate"] and slate_pages(box) == []
    assert box.notes == [f"SLATE NFL FAILED: mirror push (exit 1) — RUN BY HAND: {BLOCK} · attempt 1/3\n{MACHINE}"]


def test_a_page_ntfy_does_not_accept_is_a_failed_attempt(box, monkeypatch):
    """The push comes before the page (item 2(a): "pushes the mirror, and PAGES"): a page ntfy does not accept fails
    the attempt after the file is on the mirror, as docs/CLI.md says."""
    the_day(box, monkeypatch)
    box.page_ok = False
    assert tick(et(7, 0)) == mc.NOTIFIED
    s = slates()[0]
    assert s["failed"] == "page" and s["page"]["tries"] == 3 and box.sleeps == [10, 10]
    assert s["failure_notification"]["text"].startswith("SLATE NFL FAILED: page (ntfy did not accept it in 3 tries)")
    assert s["push"]["exit"] == 0 and box.pushes == ["slate"] and (box.repo / NFL_FILE).is_file()


def test_the_slate_waits_for_the_chain_lock_and_a_lock_held_through_the_wait_is_one_miss(box, monkeypatch):
    """The slate takes the closing's chain lock (acquire_lock): a slate and a closing never run at once. Held through
    SLATE_LOCK_WAIT_S: a miss, receipted and notified once for the day, no attempt; the next tick tries again."""
    import time as _t
    real_sleep = _t.sleep
    monkeypatch.setattr(c.time, "sleep", lambda s: real_sleep(0.01))
    monkeypatch.setattr(mc, "SLATE_LOCK_WAIT_S", 0.2)
    the_day(box, monkeypatch)
    with hold_lock():
        assert tick(et(7, 0)) == mc.NOTIFIED and tick(et(7, 1)) == mc.NOTIFIED
    assert [m["reason"] for m in misses()] == ["the chain lock was held"] and slates() == [] and box.steps == []
    assert len(box.notes) == 1 and box.notes[0].startswith("SLATE NFL 2026-10-18 MISSED: the chain lock was held "
                                                           "through the ")
    assert box.notes[0].endswith(f"-minute wait — RUN BY HAND: {BLOCK} · the watch keeps trying\n{MACHINE}")
    assert misses()[0]["queued_at"] == "2026-10-18T11:00:00Z"
    assert tick(et(7, 2)) == 0 and slates()[0]["exit"] == 0 and not any(box.lock_seen)
    # not late: the watch ticked at 07:00, the due time (the miss's tick), and the run came two minutes on
    assert (slates()[0]["late"], slates()[0]["late_minutes"]) == (False, 0) and slate_pages(box)[0]["body"] == PAGE


def test_superseded_under_the_lock_runs_nothing(box, monkeypatch):
    the_day(box, monkeypatch)
    real = mc.acquire_lock

    @contextlib.contextmanager
    def lk(timeout):
        c.append_receipt({"kind": "slate", "family": "NFL", "date": "2026-10-18", "exit": 0})   # another run's
        with real(timeout):
            yield
    monkeypatch.setattr(mc, "acquire_lock", lk)
    assert tick(et(7, 0)) == 0
    assert slates()[-1]["superseded"] is True and box.steps == box.pages == box.pushes == []


def test_every_game_started_before_a_slate_ran_is_one_miss(box, monkeypatch):
    the_day(box, monkeypatch)
    assert tick(et(13, 30)) == mc.NOTIFIED and tick(et(13, 31)) == mc.NOTIFIED    # 09:30 and 13:00 both started
    assert [m["reason"] for m in misses()] == ["every game of the day had started"] and slates() == []
    assert box.notes[-1] == f"SLATE NFL 2026-10-18 MISSED: every game of the day had started — no slate run\n{MACHINE}"


def test_a_late_run_slates_only_the_games_not_started(box, monkeypatch):
    the_day(box, monkeypatch)
    box.docs["NFL"]["predictions"] = box.docs["NFL"]["predictions"][1:]          # 601 started: not exported
    assert tick(et(9, 40)) == 0                                                  # the laptop woke at 09:40
    s = slates()[0]
    assert [x["match_id"] for x in s["covers"]] == [602] and s["late_minutes"] == 160
    assert s["steps"][0]["command"].endswith("--match-ids 602")


def test_dry_run_prints_the_slate_plan_and_touches_nothing(box, monkeypatch, capsys):
    the_day(box, monkeypatch)
    assert mc.watch(dry_run=True, now=et(6, 0), families=("NFL",)) == 0
    assert "SLATE NFL 2026-10-18: first kickoff 09:30 ET · due 07:00 ET · success no · attempts 0/3 → not yet (due " \
           "07:00 ET)" in capsys.readouterr().out
    assert mc.watch(dry_run=True, now=et(7, 0), families=("NFL",)) == 0
    out = capsys.readouterr().out
    assert "→ would RUN" in out and f"6. python cli.py export-nfl-predictions --desk --out {NFL_FILE}" in out
    assert receipts() == [] and box.steps == box.pages == box.notes == box.pushes == []
    assert not (box.repo / NFL_FILE).exists() and not (box.tmp / "backups").exists()


# ============================================================================================ the pure parts ==

def test_the_slate_file_is_the_familys_slate_kind_and_soccer_takes_its_prematch_window():
    """The names the prematch chains write (the family's export_glob, so last_calls and coverage read them as the
    slate kind). SOCCER: soccer-prematch's --start {sat} --end {sat_plus3} for the round holding the day (Saturday to
    Tuesday: the Saturday on or before it; Wednesday to Friday: the midweek override's form, the day + 3)."""
    for fam in mc.FAMILIES:
        assert fnmatch.fnmatch(mc.slate_file(fam, D18), mc.FAMILIES[fam]["export_glob"]), fam
        assert not mc.slate_file(fam, D18).startswith("closing_")
    assert mc.slate_file("MLB", D18) == "mlb_MLB_2026-10-18.json"
    assert mc.slate_file("NFL", D18) == "nfl_predictions_2026-10-18.json"
    assert mc.slate_file("SOCCER", D18) == "soccer_PL_2026-10-17_to_2026-10-20.json"    # addendum 126 item 4's file
    win = {d: mc.soccer_window(date(2026, 10, d)) for d in range(17, 25)}
    assert win == {17: ("2026-10-17", "2026-10-20"), 18: ("2026-10-17", "2026-10-20"),
                   19: ("2026-10-17", "2026-10-20"), 20: ("2026-10-17", "2026-10-20"),
                   21: ("2026-10-21", "2026-10-24"), 22: ("2026-10-22", "2026-10-25"),
                   23: ("2026-10-23", "2026-10-26"), 24: ("2026-10-24", "2026-10-27")}
    assert mc.slate_block("SOCCER", D18) == "block_1018_soccer_slate.txt"


def test_the_slate_steps_are_the_closings_own_with_the_export_sent_to_exports():
    """resolve_steps for the day's games, every step but the export word for word; the export step is the closing
    chain's with its --out sent to exports/<slate file> (SOCCER adds its window). Every option is the cli's own (law 1:
    click parses each step)."""
    import cli
    games = [{"match_id": 401, "start": et(9, 30)}, {"match_id": 402, "start": et(12, 0)}]
    for fam in mc.FAMILIES:
        got = mc.slate_steps(fam, D18, games, BASE, "RID")
        clo = mc.resolve_steps(fam, et(9, 30), games, BASE, "RID")
        assert got[:-1] == clo[:-1] and got[-1][0] == clo[-1][0] and "--desk" in got[-1]
        assert got[-1][got[-1].index("--out") + 1] == f"exports/{mc.slate_file(fam, D18)}"
        assert not any("logs/" in a for s in got for a in s)
        for s in got:
            cli.cli.commands[s[0]].make_context(s[0], list(s[1:]))               # an unknown option fails here
    soc = mc.slate_steps("SOCCER", D18, games, BASE, "RID")[-1]
    assert soc == ["export-predictions", "--sport", "soccer", "--competition", "PL", "--status", "scheduled", "--desk",
                   "--start", "2026-10-17", "--end", "2026-10-20", "--out",
                   "exports/soccer_PL_2026-10-17_to_2026-10-20.json"]
    # the cli's own default name for that window is the same file (export-predictions, law 1)
    src = inspect.getsource(cli.cli.commands["export-predictions"].callback)
    assert 'stamp = f"{start_str}_to_{end_str}"' in src
    assert 'out_path = f"exports/{sport_enum.value}{comp_part}_{stamp}.{suffix}"' in src


def test_the_counts_name_every_call_kind():
    doc = {"predictions": [{"desk": {"call": "PLAY"}}, {"desk": {"call": "PASS"}}, {"desk": {"call": "PASS"}},
                           {"desk": {"call": "LADDER"}}, {"match_id": 9}]}
    rows, calls = mc.slate_calls(doc)
    assert (rows, calls) == (5, {"PLAY": 1, "PASS": 2, "LADDER": 1, "no desk call": 1})
    assert mc.calls_text(calls) == "PLAY 1 · PASS 2 · LADDER 1 · no desk call 1"
    assert mc.calls_text(mc.slate_calls({"predictions": [{"desk": {"call": "PASS"}}]})[1]) == "PLAY 0 · PASS 1"


def test_the_closing_constants_are_unchanged():
    assert (mc.RUN_LEAD_MIN, mc.COVER_MIN, mc.PAGE_BY_MIN, mc.NO_ATTEMPT_INSIDE_MIN, mc.MAX_ATTEMPTS) == (35, 10, 30, 5, 3)
    assert mc.failure_text("NFL", "2026-10-11T17:00:00Z", failed="step 3", attempt=1) == (
        "Closing NFL 2026-10-11 13:00 ET: FAILED: step 3 · attempt 1/3")


# ==================================================================== the closings first, on a moving clock ==
# Item 2(a): "The closing runs at T-35 are unchanged." One watch process runs one thing at a time: the units start the
# next tick at the next whole minute after a tick ends (launchd, the host's oneshot timer). These tests run the real
# watch() on its production path (no fixed `now`: clock() per run) with a clock that each step moves 45 seconds, slate
# and closing steps alike, and pin that a slate never delays a closing past its T-35 nor its page past T-30.

class Clock:
    def __init__(self, t):
        self.t = t

    def time(self):
        return self.t.timestamp()

    def sleep(self, s):
        self.t += timedelta(seconds=s)


STEP_S = 45


def moving_day(box, monkeypatch, games, mlb_first_pitch=None):
    """Sunday 2026-10-18 from midnight ET: `games` (match_id, comp, start (aware), home); the NFL and MLB exports as
    the steps write them; the clock moved STEP_S by every step."""
    base = et(0, 0)
    db = box.tmp / "moving.db"
    make_db(db, [(mid, comp, int((st - base).total_seconds() // 60), "SCHEDULED", home)
                 for mid, comp, st, home in games], now=base)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    box.db = db
    k = {"comp": "NFL", "series": "KXNFLGAME", "now": base}
    box.docs["NFL"] = dp.annotate({"sport": "nfl", "predictions": [
        row(601, "London", 0.62, fair_h=0.55, bid=0.54, ask=0.55, minutes=9 * 60 + 30, **k),
        row(602, "Buffalo", 0.52, fair_h=0.515, bid=0.51, ask=0.52, minutes=13 * 60, **k)]}, now=base)
    if mlb_first_pitch:
        box.docs["MLB"] = dp.annotate({"sport": "mlb", "predictions": [
            row(701, "Underhill", 0.52, fair_h=0.51, bid=0.50, ask=0.51,
                minutes=int((mlb_first_pitch - base).total_seconds() // 60), now=base)]}, now=base)
    box.slate_on()
    clk = Clock(base)
    monkeypatch.setattr(mc, "clock", lambda: clk.t)
    monkeypatch.setattr(mc, "time", clk)
    inner = box.fake_step

    def timed_step(argv, run_id):
        out = inner(argv, run_id)
        clk.t += timedelta(seconds=STEP_S)
        return out
    monkeypatch.setattr(mc, "run_step", timed_step)
    return clk


def drive(clk, fams, t0, t1):
    """Ticks as the units fire them: the next whole minute after a tick ends."""
    clk.t = t0
    while clk.t <= t1:
        start = clk.t
        mc.watch(families=fams)
        clk.t = (clk.t.replace(second=0, microsecond=0) + timedelta(minutes=1)) if clk.t > start else (
            start + timedelta(minutes=1))


def fake_lock(monkeypatch, clk, held_from, held_to):
    """Another process holds the chain lock [held_from, held_to) on the moving clock; a wait past its timeout raises
    TimeoutError when the timeout has passed (as sp_common.db_lock)."""
    @contextlib.contextmanager
    def lock(timeout_s):
        if held_from <= clk.t < held_to:
            wait = (held_to - clk.t).total_seconds()
            if timeout_s is not None and wait > timeout_s:
                clk.t += timedelta(seconds=timeout_s)
                raise TimeoutError("held")
            clk.t = held_to
        yield
    monkeypatch.setattr(mc, "acquire_lock", lock)


def closing_1300():
    (r,) = [x for x in runs("NFL") if x["start"] == "2026-10-18T17:00:00Z"]
    start = mc.parse_utc(r["start"])
    return r, (start - mc.parse_utc(r["queued_at"])).total_seconds() / 60, (
        start - mc.parse_utc(r["page"]["at"])).total_seconds() / 60


NFL_TWO = [(601, "NFL", et(9, 30), "London"), (602, "NFL", et(13, 0), "Buffalo")]


def test_a_slate_due_minutes_before_another_familys_closing_waits_for_it(box, monkeypatch):
    """MLB's first pitch 14:50 ET: its slate is due at 12:20. NFL's 13:00 kickoff: its closing at 12:25. One watch for
    both. The slate is held (12:25 is inside the 15-minute guard), the closing is queued at 12:25 and paged by T-30,
    then the slate runs. Not late: the watch ticked at 12:20 (the hold's receipt carries that tick)."""
    clk = moving_day(box, monkeypatch, NFL_TWO + [(701, "MLB", et(14, 50), "Underhill")], mlb_first_pitch=et(14, 50))
    drive(clk, ("MLB", "NFL"), et(12, 0), et(13, 0))
    r, t_queued, t_page = closing_1300()
    assert (r["exit"], r["queued_at"], t_queued) == (0, "2026-10-18T16:25:00Z", 35.0) and t_page >= mc.PAGE_BY_MIN
    (h,) = [x for x in slates("MLB") if x.get("held")]
    assert (h["queued_at"], h["closing"]) == ("2026-10-18T16:20:00Z", {
        "family": "NFL", "start": "2026-10-18T17:00:00Z", "run_at": "2026-10-18T16:25:00Z"})
    assert h["held"] == "closing NFL 13:00 ET (T-35 12:25 ET) is inside the 15-minute guard"
    (s,) = [x for x in slates("MLB") if not x.get("held")]
    assert s["exit"] == 0 and mc.parse_utc(s["ran_at"]) >= mc.parse_utc(r["page"]["at"]) and s["late"] is False
    assert mc.slate_state("MLB", "2026-10-18") == {"success": True, "attempts": 1}           # a hold is no attempt
    assert misses("MLB") == []


def test_a_late_wake_runs_the_due_closing_first_then_the_slate(box, monkeypatch):
    """Item 2(d)'s case: the laptop's first tick after waking is 12:24 ET; the slate was due at 07:00 and the 13:00
    closing is due at 12:25. The tick at 12:24 holds the slate; the closing is queued at 12:25 and paged by T-30; the
    slate follows it, late by the minutes from 07:00 to the first tick, 12:24."""
    clk = moving_day(box, monkeypatch, NFL_TWO)
    drive(clk, ("NFL",), et(12, 24), et(13, 0))
    r, t_queued, t_page = closing_1300()
    assert (r["exit"], t_queued) == (0, 35.0) and t_page >= mc.PAGE_BY_MIN
    (s,) = [x for x in slates() if not x.get("held")]
    assert s["exit"] == 0 and mc.parse_utc(s["ran_at"]) >= mc.parse_utc(r["page"]["at"])
    assert (s["late"], s["late_minutes"], [x["match_id"] for x in s["covers"]]) == (True, 324, [602])
    assert slate_pages(box)[0]["body"].splitlines()[1] == "LATE 324 min: due 07:00 ET, run 12:24 ET"


def test_a_slate_waiting_on_a_held_lock_never_takes_it_ahead_of_a_due_closing(box, monkeypatch):
    """Another process holds the chain lock 12:18 to 12:24 ET; MLB's slate is due at 12:20, NFL's closing at 12:25. The
    slate does not queue for the lock inside the guard: the closing takes it at 12:25 and pages by T-30."""
    clk = moving_day(box, monkeypatch, NFL_TWO + [(701, "MLB", et(14, 50), "Underhill")], mlb_first_pitch=et(14, 50))
    fake_lock(monkeypatch, clk, et(12, 18), et(12, 24))
    drive(clk, ("MLB", "NFL"), et(12, 15), et(13, 0))
    r, t_queued, t_page = closing_1300()
    assert (r["exit"], t_queued) == (0, 35.0) and t_page >= mc.PAGE_BY_MIN
    (s,) = [x for x in slates("MLB") if not x.get("held")]
    assert s["exit"] == 0 and mc.parse_utc(s["ran_at"]) >= mc.parse_utc(r["page"]["at"]) and misses("MLB") == []


def test_the_slates_wait_for_the_lock_ends_at_the_guard_a_hold_not_a_miss(box, monkeypatch):
    """MLB's first pitch 14:37 ET (its slate due 12:07); NFL's closing at 12:25; the chain lock held 12:00 to 12:20.
    At 12:07 the closing is 18 minutes off, outside the guard, so the slate waits for the lock, but only until 12:10
    (15 minutes before 12:25), not the five minutes: a hold, receipted, no miss and no notice. The closing runs on
    time, the slate after it."""
    clk = moving_day(box, monkeypatch, NFL_TWO + [(701, "MLB", et(14, 37), "Underhill")], mlb_first_pitch=et(14, 37))
    fake_lock(monkeypatch, clk, et(12, 0), et(12, 20))
    drive(clk, ("MLB", "NFL"), et(12, 7), et(13, 0))
    r, t_queued, t_page = closing_1300()
    assert (r["exit"], t_queued) == (0, 35.0) and t_page >= mc.PAGE_BY_MIN
    (h,) = [x for x in slates("MLB") if x.get("held")]
    assert h["queued_at"] == "2026-10-18T16:07:00Z" and h["held"] == (
        "the chain lock was held into the 15-minute guard before closing NFL 13:00 ET (T-35 12:25 ET)")
    assert misses("MLB") == [] and not any("MISSED" in n or "FAILED" in n for n in box.notes)
    (s,) = [x for x in slates("MLB") if not x.get("held")]
    assert s["exit"] == 0 and mc.parse_utc(s["ran_at"]) >= mc.parse_utc(r["page"]["at"]) and s["late"] is False


def test_the_closing_ahead_and_the_guard(box, monkeypatch):
    """closing_ahead: the earliest closing the watch will still run among the tick's families, by its T-35, past ones
    included while the start is more than five minutes off; none for a family this machine refuses, inside T-5, or
    with a success. The dry run says the slate is held."""
    the_day(box, monkeypatch)
    a = mc.closing_ahead(("NFL", "MLB"), et(7, 0))
    assert (a["family"], a["start"], a["run_at"]) == ("NFL", et(9, 30), et(8, 55))
    assert mc.closing_ahead(("MLB",), et(8, 0))["run_at"] == et(12, 30)                    # 13:05 - 35
    assert mc.closing_ahead(("MLB",), et(7, 0)) is None          # due()'s schedule window: 6 hours, 13:05 is beyond
    assert mc.closing_ahead(("NFL",), et(9, 0))["start"] == et(9, 30)                      # past T-35, outside T-5
    assert mc.closing_ahead(("NFL",), et(9, 26))["start"] == et(13, 0)                     # 09:30 inside T-5
    monkeypatch.setenv("SP_SKIP_FAMILIES", "NFL")
    assert mc.closing_ahead(("NFL",), et(7, 0)) is None
    monkeypatch.delenv("SP_SKIP_FAMILIES")
    c.append_receipt({"kind": "closing", "family": "NFL", "start": "2026-10-18T13:30:00Z", "exit": 0,
                      "covers": [{"match_id": 601, "start": "2026-10-18T13:30:00Z"}]})
    assert mc.closing_ahead(("NFL",), et(8, 56))["start"] == et(13, 0)                     # 09:30 has its success
    assert mc.SLATE_GUARD_MIN == 15


def test_the_dry_run_says_a_slate_is_held(box, monkeypatch, capsys):
    """12:15 ET, MLB's slate due since 10:35 and not run: NFL's 13:00 closing (T-35 12:25) is inside the guard. The
    MLB slate checks its own feed first (a feed that does not answer is its miss, at once), then holds."""
    the_day(box, monkeypatch)
    assert mc.watch(dry_run=True, now=et(12, 15), families=("NFL", "MLB")) == 0
    out = capsys.readouterr().out
    assert ("SLATE MLB 2026-10-18: first kickoff 13:05 ET · due 10:35 ET · success no · attempts 0/3 → would check the "
            "MLB feed, then held: closing NFL 13:00 ET (T-35 12:25 ET) is inside the 15-minute guard") in out
    assert receipts() == [] and box.steps == []


@pytest.mark.parametrize("second", [False, True], ids=["alone", "a-closing-17-minutes-after"])
def test_the_dry_run_leaves_out_the_closing_its_own_tick_runs_first(box, monkeypatch, capsys, second):
    """MLB's first pitch 14:50 ET (its slate due 12:20), NFL's 13:00 closing due at 12:25. The dry run at 12:25 plans
    that closing, which the tick runs before its slates, so the closing holds nothing in the slate's plan: "would RUN"
    after it, as the same tick then does for real (the closing, then the slate). With a second NFL closing 17 minutes
    after it (13:17, T-35 12:42, outside the 13:00 group's cover) the plan says no plain RUN: the slate runs if the
    13:00 closing ends before 12:27 (12:42 less the guard), else it is held; the same tick's closing ends at 12:29:30,
    and the slate is held for 13:17."""
    games = NFL_TWO + ([(603, "NFL", et(13, 17), "Third")] if second else []) + [(701, "MLB", et(14, 50), "Underhill")]
    clk = moving_day(box, monkeypatch, games, mlb_first_pitch=et(14, 50))
    drive(clk, ("MLB", "NFL"), et(12, 20), et(12, 24))                 # the MLB slate held at 12:20
    capsys.readouterr()
    clk.t = et(12, 25)
    assert mc.watch(dry_run=True, families=("MLB", "NFL")) == 0
    out = capsys.readouterr().out
    assert "would start closing-run --family NFL --start 2026-10-18T17:00:00Z" in out
    plan = ("would RUN if they end before 12:27 ET, else held: closing NFL 13:17 ET (T-35 12:42 ET) is inside the "
            "15-minute guard" if second else "would RUN")
    assert (f"SLATE MLB 2026-10-18: first kickoff 14:50 ET · due 12:20 ET · success no · attempts 0/3 → after this "
            f"tick's closings: would check the MLB feed, then {plan}\n") in out
    n = len(receipts())
    mc.watch(families=("MLB", "NFL"))                                   # the same tick, for real
    assert [(r["kind"], r["family"], r.get("held"), r["exit"]) for r in receipts()[n:]
            if (r["kind"], r["family"]) in (("closing", "NFL"), ("slate", "MLB"))] == [
        ("closing", "NFL", None, 0),
        ("slate", "MLB", "closing NFL 13:17 ET (T-35 12:42 ET) is inside the 15-minute guard" if second else None, 0)]


# ============================================================ a closing that cannot start holds no slate ==
# An MLB closing whose feed does not answer is a miss on every tick, never a run (watch(), A6): it must not hold
# another family's slate (at 1efcacd it chained the hold through every MLB group of the day, and an on-time MNF slate
# missed its day, its only page at kickoff).

D19 = date(2026, 10, 19)                                   # a Monday (EDT, UTC-4)
MNF_MLB = [(18, 35), (18, 40), (19, 5), (19, 10), (19, 40), (20, 5), (20, 10), (20, 40)]
SERIES = {"MLB": "KXMLBGAME", "NFL": "KXNFLGAME"}


def busy_day(box, monkeypatch, day, games, feed, slate=True):
    """`day` from midnight ET on the moving clock (STEP_S a step): `games` (match_id, comp, start (aware), home), each
    family's export as its steps write it (a PLAY row per game); `feed(t)`: the MLB feed's answer at clock time t."""
    base = et(0, 0, day)
    db = box.tmp / "busy.db"
    make_db(db, [(mid, comp, int((st - base).total_seconds() // 60), "SCHEDULED", home)
                 for mid, comp, st, home in games], now=base)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    box.db = db
    rows = {}
    for mid, comp, st, home in games:
        rows.setdefault(comp, []).append(row(mid, home, 0.62, fair_h=0.55, bid=0.54, ask=0.55, comp=comp,
                                             series=SERIES[comp], now=base,
                                             minutes=int((st - base).total_seconds() // 60)))
    for comp, rs in rows.items():
        box.docs[comp] = dp.annotate({"sport": comp.lower(), "predictions": rs}, now=base)
    if slate:
        box.slate_on()
    clk = Clock(base)
    monkeypatch.setattr(mc, "clock", lambda: clk.t)
    monkeypatch.setattr(mc, "time", clk)
    monkeypatch.setattr(mc, "feed_answers", lambda: feed(clk.t))
    inner = box.fake_step

    def timed_step(argv, run_id):
        out = inner(argv, run_id)
        clk.t += timedelta(seconds=STEP_S)
        return out
    monkeypatch.setattr(mc, "run_step", timed_step)
    return clk


def mnf():
    return [(700 + i, "MLB", et(h, m, D19), f"Town{i}") for i, (h, m) in enumerate(MNF_MLB)] + [
        (607, "NFL", et(20, 15, D19), "Monday")]


def vpn_from_1730(t):
    return (True, "HTTP 200") if t < et(17, 30, D19) else (False, "URLError")


@pytest.mark.parametrize("slate", [True, False], ids=["slate-on", "slate-off"])
def test_an_mlb_closing_the_feed_cannot_start_holds_no_slate(box, monkeypatch, slate):
    """MNF 20:15 ET (its slate due 17:45) and MLB from 18:35 to 20:40 (the first group's T-35, 18:00, inside the guard
    at 17:45); the MLB feed answers until 17:30, then the VPN is on. The NFL slate runs at 17:45, on time: the MLB
    closings it would wait for are misses, never runs. The MLB slate ran at 16:05 while the feed answered. The
    closings and the closing misses are the same with the slate stage on or off (the pin: the closings unchanged)."""
    clk = busy_day(box, monkeypatch, D19, mnf(), vpn_from_1730, slate=slate)
    drive(clk, ("MLB", "NFL", "SOCCER"), et(15, 0, D19), et(21, 0, D19))
    assert [(r["family"], r["start"], r["queued_at"], r["exit"]) for r in runs()] == [
        ("NFL", "2026-10-20T00:15:00Z", "2026-10-19T23:40:00Z", 0)]                  # T-35, as without a slate
    assert sorted((r["family"], r["start"], r["reason"][:16]) for r in receipts() if r["kind"] == "closing_miss") == [
        ("MLB", mc.iso_z(et(h, m, D19)), why) for h, m in MNF_MLB        # each MLB start: the feed, then inside T-5
        for why in ("feed unreachable", "inside T-5 when ")]
    if not slate:
        assert slates("NFL") == slates("MLB") == [] and box.pushes == ["closing"]
        return
    assert [(x["queued_at"], x.get("ran_at"), x["exit"], x.get("late"), x.get("held")) for x in slates("NFL")] == [
        ("2026-10-19T21:45:00Z", "2026-10-19T21:45:00Z", 0, False, None)]          # 17:45 ET, no hold
    assert [(x["queued_at"], x["exit"]) for x in slates("MLB")] == [("2026-10-19T20:05:00Z", 0)]
    assert misses("NFL") == misses("MLB") == []
    assert [p["body"].splitlines()[0] for p in box.pages if p["title"] == "NFL slate 2026-10-19"] == [
        "SLATE NFL 2026-10-19: 1 rows · PLAY 1 · PASS 0 · exports/nfl_predictions_2026-10-19.json"]


def test_an_mlb_slate_checks_its_own_feed_before_the_guard(box, monkeypatch):
    """The MLB slate due since 10:35, its 13:05 closing's T-35 (12:30) inside the guard at 12:20, the feed down: the
    slate's own feed check comes first, so the miss pages RUN BY HAND at once, not a silent hold until the feed comes
    back."""
    the_day(box, monkeypatch)
    box.feed = (False, "URLError")
    assert tick(et(12, 20), ("MLB",)) == mc.NOTIFIED
    assert [m["reason"] for m in misses("MLB")] == ["feed unreachable"] and slates("MLB") == []
    assert box.notes == ["SLATE MLB 2026-10-18 MISSED: MLB feed unreachable: VPN on, Tailscale off — RUN BY HAND: "
                         f"block_1018_mlb_slate.txt · the watch keeps trying\n{MACHINE}"]


def test_the_guard_probes_the_feed_once_and_only_for_an_mlb_closing_that_would_hold(box, monkeypatch, capsys):
    """slate_ahead: an NFL slate with an MLB closing inside the guard probes the feed once; answered, the MLB closing
    holds it; unanswered, the NFL closing ahead (20:15, T-35 19:40) is the one read. No probe when nothing MLB is
    near. The dry run (no network) says both ways."""
    clk = busy_day(box, monkeypatch, D19, mnf(), vpn_from_1730)
    calls, answers = [], [(True, "HTTP 200")]
    monkeypatch.setattr(mc, "feed_answers", lambda: calls.append(clk.t) or answers[0])
    a = mc.slate_ahead(("MLB", "NFL"), et(17, 45, D19))
    assert (a["family"], a["start"], len(calls)) == ("MLB", et(18, 35, D19), 1)    # answered: the MLB closing holds
    answers[0] = (False, "URLError")
    a = mc.slate_ahead(("MLB", "NFL"), et(17, 45, D19))
    assert (a["family"], a["start"], len(calls)) == ("NFL", et(20, 15, D19), 2)    # unanswered: the NFL closing
    assert mc.slate_ahead(("MLB", "NFL"), et(17, 0, D19))["family"] == "MLB" and len(calls) == 2   # 18:00 not near
    assert mc.slate_ahead(("MLB", "NFL"), et(17, 45, D19), feed=False)["family"] == "NFL" and len(calls) == 2
    assert mc.slate_ahead(("MLB", "NFL"), et(17, 45, D19), feed=True)["family"] == "MLB" and len(calls) == 2
    clk.t = et(17, 45, D19)
    assert mc.watch(dry_run=True, families=("MLB", "NFL")) == 0
    assert ("SLATE NFL 2026-10-19: first kickoff 20:15 ET · due 17:45 ET · success no · attempts 0/3 → held if the MLB "
            "feed answers: closing MLB 18:35 ET (T-35 18:00 ET) is inside the 15-minute guard; if it does not, would "
            "RUN") in capsys.readouterr().out
    assert len(calls) == 2 and receipts() == []


# ===================================================== a held tick's probe never costs the next closing its T-35 ==
# The #590 review's probe-delay finding: on a tick whose slates stay held anyway, the slate stage's feed probes (an MLB
# slate's own check, then the guard's) ran after the tick's closings, and their seconds carried the next tick past the
# next closing's T-35. A closing due by the next tick now holds a slate with no probe, and the slate stage probes at
# most once a tick, not at all when the tick's closings did.

D23 = date(2026, 9, 23)                                    # a Wednesday (EDT, UTC-4)


def test_a_held_ticks_probe_never_carries_the_next_closing_past_its_t35(box, monkeypatch):
    """PL 15:00 ET (closing T-35 14:25), MLB 15:05 and 19:05 ET (T-35 14:30, 18:30). The laptop wakes at 14:20 with the
    SOCCER and MLB slates due (12:30, 12:35). Each step takes 49.5 s and each MLB feed probe 3 s; the feed answers. The
    14:25 tick's SOCCER closing ends at 14:29:57 with both slates held by the MLB 15:05 closing, due at 14:30: held with
    no probe, so the 14:30 tick starts on time and its own probe queues that closing at 14:30:03, T-35.0, as with no
    slate stage (at 51e3057 two slate probes carried that tick to 14:30:03 and the closing to 14:31:03, T-34.0). From
    14:25 the one probe is the closing's; the MLB slate after it reads that answer. Each closing the slates waited for
    is receipted once, the newest naming the one they waited for last."""
    base = et(0, 0, D23)
    games = [(521, "PL", 15 * 60, "Villa"), (701, "MLB", 15 * 60 + 5, "Underhill"),
             (702, "MLB", 19 * 60 + 5, "Clearwater")]
    db = box.tmp / "wed.db"
    make_db(db, [(mid, comp, m, "SCHEDULED", home) for mid, comp, m, home in games], now=base)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    box.db = db
    box.docs["SOCCER"] = dp.annotate({"sport": "soccer", "predictions": [
        row(521, "Villa", 0.40, fair_h=0.39, fair_d=0.30, draw=0.30, bid=0.38, ask=0.39, comp="PL",
            series="KXEPLGAME", minutes=15 * 60, now=base)]}, now=base)
    box.docs["MLB"] = dp.annotate({"sport": "mlb", "predictions": [
        row(701, "Underhill", 0.52, fair_h=0.515, bid=0.51, ask=0.52, minutes=15 * 60 + 5, now=base),
        row(702, "Clearwater", 0.62, fair_h=0.55, bid=0.54, ask=0.55, minutes=19 * 60 + 5, now=base)]}, now=base)
    box.slate_on()
    clk = Clock(base)
    monkeypatch.setattr(mc, "clock", lambda: clk.t)
    monkeypatch.setattr(mc, "time", clk)
    inner, probes = box.fake_step, []

    def timed_step(argv, run_id):
        out = inner(argv, run_id)
        clk.t += timedelta(seconds=49.5)
        return out

    def slow_feed():                  # the feed answers, in 3 s on the moving clock
        probes.append(clk.t)
        clk.t += timedelta(seconds=3)
        return True, "HTTP 200"
    monkeypatch.setattr(mc, "run_step", timed_step)
    monkeypatch.setattr(mc, "feed_answers", slow_feed)
    drive(clk, ("MLB", "NFL", "SOCCER"), et(14, 20, D23), et(14, 40, D23))
    assert [(r["family"], r["start"], r["queued_at"], r["exit"]) for r in runs()] == [
        ("SOCCER", "2026-09-23T19:00:00Z", "2026-09-23T18:25:00Z", 0),
        ("MLB", "2026-09-23T19:05:00Z", "2026-09-23T18:30:03Z", 0)]            # each queued at T-35.0
    assert [p for p in probes if p >= et(14, 25, D23)] == [et(14, 30, D23)]    # the MLB closing's own probe only
    for fam in ("MLB", "SOCCER"):
        assert [(x["queued_at"], x["closing"]["family"], x["closing"]["start"]) for x in slates(fam)
                if x.get("held")] == [("2026-09-23T18:20:00Z", "SOCCER", "2026-09-23T19:00:00Z"),
                                      ("2026-09-23T18:25:00Z", "MLB", "2026-09-23T19:05:00Z")]
        (s,) = [x for x in slates(fam) if not x.get("held")]
        assert s["exit"] == 0 and mc.parse_utc(s["ran_at"]) >= mc.parse_utc(runs("MLB")[0]["page"]["at"])
    assert misses("MLB") == misses("SOCCER") == []


# ================================================================================ the receipt's declared keys ==

DECLARED = {"kind", "family", "date", "run_id", "trigger", "due", "queued_at", "ran_at", "late_minutes", "late",
            "attempt", "covers", "file", "rows", "calls", "backup", "steps", "push", "exit"}


@pytest.mark.parametrize("path", ["success", "step", "not written", "lock"])
def test_every_attempt_receipt_carries_the_declared_keys(box, monkeypatch, path):
    """Item 2(c): "`kind: "slate"` lines [...] with family, date, rows, calls, file, exit": every attempt's line carries
    the same keys, a lock that cannot be taken (anything but a timeout) included."""
    the_day(box, monkeypatch)
    if path == "step":
        box.fail_cmd["predict-nfl"] = (1, ["boom"])
    elif path == "not written":
        box.fail_cmd["export-nfl-predictions"] = (0, ["ok"])                     # exit 0, no file
    elif path == "lock":
        monkeypatch.setattr(mc, "acquire_lock",
                            lambda t: (_ for _ in ()).throw(PermissionError("lock dir not writable")))
    assert tick(et(7, 0)) == (0 if path == "success" else mc.NOTIFIED)
    (s,) = slates()
    assert DECLARED <= set(s), sorted(DECLARED - set(s))
    # the rest as the ledger says: export_written once the file is read, page once a page is tried, seconds on every
    # attempt but a lock error, step only when a step command failed
    assert {k: k in s for k in ("export_written", "page", "seconds", "step")} == {
        "success": {"export_written": True, "page": True, "seconds": True, "step": False},
        "step": {"export_written": False, "page": False, "seconds": True, "step": True},
        "not written": {"export_written": False, "page": False, "seconds": True, "step": False},
        "lock": {"export_written": False, "page": False, "seconds": False, "step": False}}[path]
    if path == "lock":
        assert (s["failed"], s["attempt"], s["ran_at"], s["late"], s["late_minutes"], s["rows"], s["calls"]) == (
            "lock", 1, "2026-10-18T11:00:00Z", False, 0, None, None)
        assert [x["match_id"] for x in s["covers"]] == [601, 602] and s["error"].startswith("PermissionError")


ITEM_2C = {"family", "date", "rows", "calls", "file", "exit"}


@pytest.mark.parametrize("line", ["held", "refused", "superseded"])
def test_the_lines_that_are_no_attempt_carry_the_item_2c_keys_too(box, monkeypatch, line):
    """Item 2(c): "`kind: "slate"` lines beside the closing lines, with family, date, rows, calls, file, exit": a hold,
    a refusal and a superseded run carry them as well (rows and calls null: nothing was written)."""
    if line == "held":
        clk = moving_day(box, monkeypatch, NFL_TWO)
        drive(clk, ("NFL",), et(12, 24), et(12, 24))                   # the 13:00 closing's T-35 is a minute off
    else:
        the_day(box, monkeypatch)
        if line == "refused":
            monkeypatch.setenv("SP_SKIP_FAMILIES", "NFL")
        else:
            real = mc.acquire_lock

            @contextlib.contextmanager
            def lk(timeout):
                c.append_receipt({"kind": "slate", "family": "NFL", "date": "2026-10-18", "exit": 0})
                with real(timeout):
                    yield
            monkeypatch.setattr(mc, "acquire_lock", lk)
        tick(et(7, 0))
    (s,) = [x for x in slates() if x.get(line)]
    assert ITEM_2C <= set(s), sorted(ITEM_2C - set(s))
    assert (s["rows"], s["calls"]) == (None, None)


def test_the_help_text_shows_the_declared_block_name_whole():
    """`closing-watch --help` quotes the failure page; click joins a wrapped docstring line with a space, so the block
    name (block_<MMDD>_<family>_slate.txt, as the page sends it) must sit whole on one source line."""
    from click.testing import CliRunner

    import cli
    out = CliRunner().invoke(cli.cli, ["closing-watch", "--help"], terminal_width=200).output
    assert ("SLATE <FAMILY> FAILED: <step> — RUN BY HAND: block_<MMDD>_<family>_slate.txt · attempt k/3"
            in " ".join(out.split()))
