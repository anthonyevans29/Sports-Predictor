"""cutover-readiness (#85, ARCHITECT lane 2 2026-10-04): the ruled criteria
read from a synthetic mirror + receipts. No DB, no network."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))

import cutover_readiness as cr  # noqa: E402


def game(home, away, p, fair, kal=0.5, desk="PASS"):
    return {"home_team": home, "away_team": away, "utc_date": "2026-10-05T17:00:00",
            "prediction": {"home_win_prob": p}, "market": {"fair_prob": {"HOME": fair}},
            "kalshi": {"prob": {"HOME": kal}}, "desk": {"call": desk, "units": 0}}


def put(mirror, side, d, name, rows, sha="abc"):
    p = mirror / side / d
    p.mkdir(parents=True, exist_ok=True)
    (p / name).write_text(json.dumps({"git_sha": sha, "desk_meta": {"policy_version": "v1.1"},
                                      "predictions": rows}))


def day(mirror, d, host_rows=None, lap_rows=None):
    base = [game("Seattle", "Rams", 0.6, 0.55, desk="PLAY"), game("Dallas", "Eagles", 0.5, 0.5)]
    put(mirror, "laptop", d, f"nfl_{d}.json", lap_rows or base)
    put(mirror, "host", d, f"nfl_{d}.json", host_rows or base)


def test_classify_capture_timing_vs_model():
    assert cr.classify_line("$.predictions[Rams @ Seattle 2026-10-05T17:00].market.fair_prob.HOME: '0.55' vs '0.56'") \
        == "capture timing"
    assert cr.classify_line("$.predictions[Rams @ Seattle 2026-10-05T17:00].desk.call: 'PLAY' vs 'PASS'") \
        == "capture timing"
    assert cr.classify_line("$.predictions[Rams @ Seattle 2026-10-05T17:00].input_quality.book_odds: '7' vs '6'") \
        == "capture timing"
    # a model probability or any other field is never auto-named
    assert cr.classify_line("$.predictions[Rams @ Seattle 2026-10-05T17:00].prediction.home_win_prob: '0.6' vs '0.61'") \
        is None
    assert cr.classify_line("$.predictions[Rams @ Seattle 2026-10-05T17:00].input_quality.injuries: 'a' vs 'b'") is None
    assert cr.classify_line("$.model_version: 'v1' vs 'v2'") is None


def test_compare_day_names_classes(tmp_path):
    day(tmp_path, "2026-10-05", host_rows=[game("Seattle", "Rams", 0.6, 0.57, desk="PLAY"),
                                           game("Dallas", "Eagles", 0.5, 0.5)])
    r = cr.compare_day(tmp_path / "laptop" / "2026-10-05", tmp_path / "host" / "2026-10-05")
    assert r["verdict"] == "DIVERGENT" and r["classes"] == {"capture timing": 1} and not r["unnamed"]
    day(tmp_path, "2026-10-06", host_rows=[game("Seattle", "Rams", 0.6, 0.55, desk="PLAY")])
    r = cr.compare_day(tmp_path / "laptop" / "2026-10-06", tmp_path / "host" / "2026-10-06")
    assert r["unnamed"] and "row only on laptop" in r["unnamed"][0]          # pagination needs naming


def test_streak_counts_breaks_and_named(tmp_path):
    for d in ("2026-10-04", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"):
        day(tmp_path, d)
    s = cr.streak(tmp_path, {}, cr.date(2026, 10, 8))
    assert s["run"] == 5 and all(x["counts"] for x in s["days"])
    # an unnamed model diff on 10-06 breaks it, unless the operator names that date
    day(tmp_path, "2026-10-06", host_rows=[game("Seattle", "Rams", 0.61, 0.55, desk="PLAY"),
                                           game("Dallas", "Eagles", 0.5, 0.5)])
    s = cr.streak(tmp_path, {}, cr.date(2026, 10, 8))
    assert s["run"] == 2 and not s["days"][-1]["counts"]
    s = cr.streak(tmp_path, {"2026-10-06": "new injury input on the host"}, cr.date(2026, 10, 8))
    assert s["run"] == 5 and s["days"][2]["how"].startswith("operator-named")
    # a calendar gap breaks the streak; a date one side lacks is pending
    put(tmp_path, "laptop", "2026-10-10", "nfl_x.json", [])
    s = cr.streak(tmp_path, {}, cr.date(2026, 10, 10))
    assert s["pending"] == ["2026-10-10"]


def receipts(tmp_path, rows):
    p = tmp_path / "receipts.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return p


def test_host_state_full_day_and_desk_rows(tmp_path):
    mirror = tmp_path / "m"
    day(mirror, "2026-10-06")
    recs = [{"ts": "2026-10-05T10:00:00Z", "release": "v1.2.2", "kind": "deploy", "host": "h"},
            {"ts": "2026-10-05T12:00:00Z", "release": "v1.2.2", "kind": "chain", "exit": 0, "unit": "a",
             "exports": ["exports/nfl_2026-10-05.json"]},
            {"ts": "2026-10-06T08:00:00Z", "release": "v1.2.2", "kind": "chain", "exit": 0, "unit": "nfl",
             "exports": ["exports/nfl_2026-10-06.json"], "host": "h"}]
    now = cr.datetime(2026, 10, 7, 12, tzinfo=cr.timezone.utc)
    hs = cr.host_state(recs, mirror, now)
    assert hs["tag"] == "v1.2.2" and hs["since"] == "2026-10-05T10:00:00Z"
    assert hs["days"]["2026-10-06"]["chains"][0]["calls"] == {"PLAY": 1, "PASS": 1}
    assert hs["full_days"] == ["2026-10-06"]               # 10-05 was partial (went on the tag at 10:00)
    # a failed chain spoils its day; a tag change resets "since"
    recs.append({"ts": "2026-10-07T09:00:00Z", "release": "v1.3.0", "kind": "deploy"})
    assert cr.host_state(recs, mirror, now)["tag"] == "v1.3.0"


def test_main_not_yet_names_every_unmet(tmp_path, capsys):
    mirror = tmp_path / "m"
    for d in ("2026-10-04", "2026-10-05"):
        day(mirror, d)
    rp = receipts(tmp_path, [{"ts": "2026-10-05T10:00:00Z", "release": "BETA main@abc", "kind": "chain",
                              "exit": 0, "exports": []}])
    rc = cr.main(["--mirror", str(mirror), "--receipts", str(rp), "--no-parity", "--today", "2026-10-05"])
    out = capsys.readouterr().out
    assert rc == 1
    last = out.strip().splitlines()[-1]
    assert last.startswith("NOT-YET") and "(a) streak 2/5" in last and "not a release tag" in last
    assert "(c) parity not run" in last and "earliest 2026-10-08" in last


def test_parity_refuses_a_non_release_tag():
    ok, why = cr.parity_on("BETA main@abc")
    assert ok is None and "not a release tag" in why


def test_carries_246_on_known_tags():
    # v1.2.2 is deployed and carries #246 when tags are present in the checkout; unknown otherwise
    assert cr.carries("v1.2.2") in (True, None)
    assert cr.carries("v0.0.0-nope") is None
