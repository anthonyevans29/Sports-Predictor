"""NFL INJURY-READ RECEIPT (#627; ARCHITECT 2026-10-23, addendum 162 item 3(c)): closing files and closing receipts in
a throwaway directory, a fake provider for --live; no network and no database."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("nir", ROOT / "scripts" / "nfl_injury_receipt.py")
nir = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nir)


def _side(count, unresolved=(), synced="2026-10-18T16:25:00"):
    return {"count": count, "qb_listed": [], "positions_unresolved": list(unresolved), "synced_at": synced}


def _row(home, away, h, a):
    return {"match_id": 1, "home_team": home, "away_team": away, "input_quality": {"injuries": {"home": h, "away": a}}}


def world(tmp_path):
    ex = tmp_path / "exports"
    ex.mkdir()
    # the 10-18 13:00 ET closing: IND empty (the feed said so), NE empty (not named: our read), one join failure
    (ex / "closing_NFL_2026-10-18T1700Z.json").write_text(json.dumps({
        "closing": {"family": "NFL", "start": "2026-10-18T17:00:00Z", "run_id": "r1"},
        "predictions": [_row("Indianapolis Colts", "New England Patriots", _side(0, synced=None), _side(0)),
                        _row("Chicago Bears", "Detroit Lions", _side(6, ["J. Doe"], "2026-10-18T16:25:00"),
                             _side(4, synced="2026-10-18T14:00:00"))]}))
    # the 10-18 16:25 ET closing: LV empty, no receipt for its run
    (ex / "closing_NFL_2026-10-18T2025Z.json").write_text(json.dumps({
        "closing": {"family": "NFL", "start": "2026-10-18T20:25:00Z", "run_id": "r2"},
        "predictions": [_row("Las Vegas Raiders", "Denver Broncos", _side(0), _side(3, synced="2026-10-18T19:50:00"))]}))
    (ex / "closing_SOCCER_2026-10-18T1100Z.json").write_text(json.dumps({"closing": {"family": "SOCCER"}}))
    (ex / "closing_NFL_2026-10-04T1700Z.json").write_text(json.dumps({     # before --since: not read
        "closing": {"family": "NFL", "start": "2026-10-04T17:00:00Z", "run_id": "r0"}, "predictions": []}))
    rec = tmp_path / "receipts.jsonl"
    rec.write_text("\n".join(json.dumps(x) for x in [
        {"kind": "closing", "family": "NFL", "run_id": "r1", "injury_lists_empty": ["Indianapolis Colts"],
         "steps": [{"step": 2, "command": "python cli.py sync-injuries --competition NFL --season 2026 --match-ids 1 "
                    "--strict", "exit": 0, "empty_answers": ["Indianapolis Colts"]}]},
        {"kind": "step", "run_id": "r2"}]) + "\nnot json\n")
    return ex, rec


def run(tmp_path, *args, get=None):
    ex, rec = world(tmp_path)
    out = []
    assert nir.main(["--exports", str(ex), "--receipts", str(rec), *args], echo=out.append, get=get) == 0
    return "\n".join(out)


def test_per_closing_empty_lists_by_cause_join_failures_and_observation_age(tmp_path):
    out = run(tmp_path)
    assert "closing_NFL_2026-10-04" not in out and "SOCCER" not in out
    assert ("empty lists (count 0): Indianapolis Colts: FEED (the provider answered no entry); New England Patriots: "
            "OUR READ (the provider answered; nothing retained)") in out
    assert "join failures (positions unresolved): Chicago Bears 1" in out
    # r1 at 17:00Z: NE 35 min, CHI 35, DET 180 (IND has no synced_at)
    assert "observation age (start - synced_at): median 35 min · largest 180 min (Detroit Lions) · no synced_at: " \
           "Indianapolis Colts" in out
    assert "run r2 · teams 2 · receipt NOT FOUND" in out
    assert "Las Vegas Raiders: UNKNOWN (no receipt for the run)" in out
    assert ("T totals: closings 2 · team-readings 6 · empty lists FEED 1 · OUR READ 1 · UNKNOWN 1 · join failures 1 · "
            "no synced_at 1") in out


def test_live_reads_raw_taken_retained_and_unresolved_without_a_lookup(tmp_path):
    calls = []

    def get(path, **p):
        calls.append(path)
        if path == "teams":
            return 200, {}, [{"id": 7, "name": "Colts"}, {"id": 8, "name": "Patriots"}]
        if path == "players":
            return 200, {}, [{"id": 70, "name": "A. Passer", "position": "QB"}] if p["team"] == 7 else []
        if path == "injuries":
            if p["team"] == 7:
                return 200, {}, [{"player": {"id": 70, "name": "A. Passer"}, "status": "Out"},
                                 {"player": {"id": 70, "name": "A. Passer"}, "status": "Out"},       # one id twice
                                 {"player": {"id": 71, "name": "B. Unknown"}, "status": "Questionable"}]
            return 200, {}, []
        return 200, {}, []
    out = run(tmp_path, "--live", "--save", str(tmp_path / "pay"), get=get)
    assert "7 Colts: raw 3 · taken 2 · retained 2 · positions unresolved 1 (B. Unknown)" in out
    assert "8 Patriots: raw 0 · taken 0 · retained 0 · positions unresolved 0 · roster EMPTY" in out
    assert "live totals: raw 3 · taken 2 · retained 2 · positions unresolved 1 · teams answering empty 1 · rosters " \
           "empty 1" in out
    assert "position" not in "".join(c for c in calls if c not in ("teams", "players", "injuries"))   # no lookup asked
    assert (tmp_path / "pay" / "injuries_7.json").is_file()


def test_live_payloads_are_refused_under_data(tmp_path):
    with pytest.raises(SystemExit, match="under data/"):
        run(tmp_path, "--live", "--save", str(ROOT / "data" / "x"), get=lambda *a, **k: (200, {}, []))
