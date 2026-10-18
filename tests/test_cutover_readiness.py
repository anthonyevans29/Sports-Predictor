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


def test_missing_chain_exit_is_never_a_full_day(tmp_path, capsys, monkeypatch):
    """#273 review (reproduced on 9757e76c): a chain receipt with no exit was read as a success. Success is
    explicit — integer exit 0, nothing refused, every counted step run; a missing exit is a failure."""
    mirror = tmp_path / "m"
    day(mirror, "2026-10-06")
    base = {"release": "v1.2.2", "kind": "chain", "unit": "nfl", "exports": ["exports/nfl_2026-10-06.json"]}
    now = cr.datetime(2026, 10, 7, 12, tzinfo=cr.timezone.utc)
    deploy = {"ts": "2026-10-05T10:00:00Z", "release": "v1.2.2", "kind": "deploy"}
    no_exit = cr.host_state([deploy, {**base, "ts": "2026-10-06T08:00:00Z"}], mirror, now)
    assert no_exit["full_days"] == [] and no_exit["days"]["2026-10-06"]["chains"][0]["state"] == "failed (exit missing)"
    partial = cr.host_state([deploy, {**base, "ts": "2026-10-06T08:00:00Z", "exit": 0, "steps_ok": 3,
                                      "steps_total": 5}], mirror, now)
    assert partial["full_days"] == [] and "steps 3/5" in partial["days"]["2026-10-06"]["chains"][0]["state"]
    ok = cr.host_state([deploy, {**base, "ts": "2026-10-06T08:00:00Z", "exit": 0, "steps_ok": 5,
                                 "steps_total": 5}], mirror, now)
    assert ok["full_days"] == ["2026-10-06"]
    rp = receipts(tmp_path, [deploy, {**base, "ts": "2026-10-06T08:00:00Z"}])
    # tag containment is not the subject here, and CI's depth-1 checkout carries no tags (it would read
    # "unknown" before the full-day check): pin it so the line names the missing full day
    monkeypatch.setattr(cr, "carries", lambda tag, commit=cr.CARRY_246: True)
    assert cr.main(["--mirror", str(mirror), "--receipts", str(rp), "--no-parity", "--today", "2026-10-09"]) == 1
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert last.startswith("NOT-YET") and "(b) no full day on v1.2.2 yet" in last


def test_newer_one_sided_date_blocks_the_older_streak_unless_it_is_todays_pending_push(tmp_path, capsys):
    """#273 review (reproduced on 9757e76c): a newer host-only date left the older five-day streak intact
    and permitted GO. One-sided dates older than today (the declared clock) are OVERDUE and the streak reads
    0; only today's one-sided date is a pending morning push."""
    mirror = tmp_path / "m"
    for d in ("2026-10-04", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"):
        day(mirror, d)
    put(mirror, "host", "2026-10-09", "nfl_2026-10-09.json", [game("Seattle", "Rams", 0.6, 0.55)])
    overdue = cr.streak(mirror, {}, cr.date(2026, 10, 10))                  # 10-09 host-only, today 10-10
    assert overdue["run"] == 0 and overdue["overdue"] == ["2026-10-09"] and "overdue" in overdue["days"][0]["break"]
    pending = cr.streak(mirror, {}, cr.date(2026, 10, 9))                   # 10-09 IS today: pending, streak holds
    assert pending["run"] == 5 and pending["pending"] == ["2026-10-09"] and pending["overdue"] == []
    stale = cr.streak(mirror, {}, cr.date(2026, 10, 12))                    # nothing since 10-08 (10-09 overdue)
    assert stale["run"] == 0
    rp = receipts(tmp_path, [{"ts": "2026-10-05T10:00:00Z", "release": "v1.2.2", "kind": "deploy"}])
    assert cr.main(["--mirror", str(mirror), "--receipts", str(rp), "--no-parity", "--today", "2026-10-10"]) == 1
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert last.startswith("NOT-YET") and "(a) streak 0/5 (overdue one-sided 2026-10-09)" in last


# ---------------------------------------------------------------- (T9) the weekly full-season list
# ARCHITECT 2026-10-18, addendum 122 item 3(b): "`cutover-readiness` gains a readout line from SP_FULLSEASON_LIST —
# "fullseason list: N competitions" or "EMPTY → NOT-YET" (one more binding condition on the readout [...])".

import pytest  # noqa: E402

import sp_common as c  # noqa: E402
import sp_run  # noqa: E402

EXAMPLE = ROOT / "deploy" / "hosting" / "etc" / "fullseason.list.example"


@pytest.fixture
def no_settings(tmp_path, monkeypatch):
    """SP_FULLSEASON_LIST from nowhere but the test: no environment value, no host.env, no checkout .env."""
    monkeypatch.delenv("SP_FULLSEASON_LIST", raising=False)
    monkeypatch.setattr(c, "HOST_ENV", tmp_path / "no-host.env")
    monkeypatch.setattr(c, "_DOTENV_CACHE", {})
    return tmp_path


def readout(tmp_path, capsys, *extra):
    """cr.main with (a)-(c) unmet the cheap way (no mirror, no receipts, no parity); returns (exit, T9 lines,
    last line)."""
    rc = cr.main(["--mirror", str(tmp_path / "no-mirror"), "--receipts", str(tmp_path / "no-receipts.jsonl"),
                  "--no-parity", "--today", "2026-10-18", *extra])
    out = capsys.readouterr().out.strip().splitlines()
    i = next(n for n, ln in enumerate(out) if ln.startswith("(T9) WEEKLY FULL-SEASON LIST"))
    t9 = [ln for ln in out[i:-1] if ln.strip()]
    return rc, t9, out[-1]


def test_t9_populated_list_counts_its_competitions_and_does_not_bind(no_settings, monkeypatch, capsys):
    lst = no_settings / "fullseason.list"
    lst.write_text("# generated from the host DB, read-only (T9)\n\nPL|2026/27\n  NFL | 2026  \nNHL|2026\n")
    monkeypatch.setenv("SP_FULLSEASON_LIST", str(lst))
    rc, t9, last = readout(no_settings, capsys)
    assert t9[0] == f"(T9) WEEKLY FULL-SEASON LIST — SP_FULLSEASON_LIST: {lst}"
    assert t9[1] == "    fullseason list: 3 competitions — PL|2026/27 · NFL|2026 · NHL|2026"
    assert t9[2] == "    MLB lines: none (MLB is excluded by ruling, addendum 122 item 3(a))"
    assert rc == 1 and last.startswith("NOT-YET") and "(T9)" not in last      # (a)-(c) unmet here; T9 is not


def test_t9_the_installed_example_reads_empty_not_yet(no_settings, monkeypatch, capsys):
    """The host's file today: the installed example, comment lines only (addendum 122 item 3)."""
    monkeypatch.setenv("SP_FULLSEASON_LIST", str(EXAMPLE))
    rc, t9, last = readout(no_settings, capsys)
    assert t9[1] == "    fullseason list: EMPTY → NOT-YET · the file lists no competitions (blank and '#' lines only)"
    assert rc == 1 and "(T9) fullseason list EMPTY" in last
    with pytest.raises(SystemExit, match="lists no competitions"):       # the chain refuses the same file
        sp_run.fullseason_steps()


def test_t9_missing_setting_and_missing_file_are_not_yet_with_the_reason(no_settings, monkeypatch, capsys):
    rc, t9, last = readout(no_settings, capsys)
    assert t9[0] == "(T9) WEEKLY FULL-SEASON LIST — SP_FULLSEASON_LIST: not set"
    assert t9[1].startswith("    fullseason list: NOT SET → NOT-YET · SP_FULLSEASON_LIST is not set on this machine")
    assert rc == 1 and "(T9) fullseason list NOT SET" in last
    with pytest.raises(SystemExit, match="SP_FULLSEASON_LIST missing"):
        sp_run.fullseason_steps()
    monkeypatch.setenv("SP_FULLSEASON_LIST", str(no_settings / "absent.list"))
    rc, t9, last = readout(no_settings, capsys)
    assert t9[1] == "    fullseason list: MISSING → NOT-YET · the file does not exist (hosting-h1.md step T9 writes it)"
    assert "(T9) fullseason list MISSING" in last
    with pytest.raises(SystemExit, match="SP_FULLSEASON_LIST missing"):
        sp_run.fullseason_steps()


def test_t9_unreadable_or_unparseable_is_never_ok(no_settings, monkeypatch, capsys):
    """Law 4: a file the readout cannot read, or a line the chain cannot parse, is NOT-YET, never a count."""
    d = no_settings / "a-directory"
    d.mkdir()
    monkeypatch.setenv("SP_FULLSEASON_LIST", str(d))
    rc, t9, last = readout(no_settings, capsys)
    assert t9[1].startswith("    fullseason list: UNREADABLE → NOT-YET · unreadable (IsADirectoryError")
    assert "(T9) fullseason list UNREADABLE" in last
    lst = no_settings / "fullseason.list"
    lst.write_text("PL|2026/27\n")
    monkeypatch.setenv("SP_FULLSEASON_LIST", str(lst))

    def denied(self, *a, **k):
        raise PermissionError(13, "Permission denied", str(self))
    with monkeypatch.context() as m:                    # root reads a 0000 file, so the denial is simulated
        m.setattr(cr.Path, "read_text", denied)
        rc, t9, last = readout(no_settings, capsys)
    assert t9[1].startswith("    fullseason list: UNREADABLE → NOT-YET · unreadable (PermissionError")
    assert "(T9) fullseason list UNREADABLE" in last
    lst.write_text("PL|2026/27\nNFL 2026\n")
    rc, t9, last = readout(no_settings, capsys)
    assert t9[1] == (f"    fullseason list: UNPARSEABLE → NOT-YET · {lst} line 2: 'NFL 2026' is not CODE|SEASON "
                     f"(weekly-fullseason fails on this line too)")
    assert "(T9) fullseason list UNPARSEABLE" in last
    with pytest.raises(ValueError, match="line 2: 'NFL 2026' is not CODE|SEASON"):
        sp_run.fullseason_steps()


def test_t9_count_is_fullseason_steps_own_resolution(no_settings, monkeypatch, capsys):
    """One parser, one formatting: the readout's competitions are exactly the steps weekly-fullseason resolves from the
    same file (blank lines, indented comments, padding round '|', a repeated line, a '|' inside the season, a doubled
    brace the chain's str.format turns into one), and a brace the chain cannot fill fails both: resolve() raises,
    the readout reads UNPARSEABLE with the chain's own message (before: the readout counted it, ok)."""
    lst = no_settings / "fullseason.list"
    lst.write_text("# head\n\n   # indented comment\nPL|2026/27\n BL1 |  2026/27 \nNFL|2026\nPL|2026/27\nX|a|b\n"
                   "Y|{{b}}\n")
    monkeypatch.setenv("SP_FULLSEASON_LIST", str(lst))
    steps = sp_run.fullseason_steps()
    assert steps == sp_run.resolve("weekly-fullseason", {}, cr.date(2026, 10, 25))
    st = cr.fullseason_state(c.setting("SP_FULLSEASON_LIST"))
    assert st["state"] == "ok" and len(st["entries"]) == len(steps) == 6
    assert st["entries"] == [f"{s[2]}|{s[4]}" for s in steps]
    assert st["entries"] == ["PL|2026/27", "BL1|2026/27", "NFL|2026", "PL|2026/27", "X|a|b", "Y|{b}"]
    # a brace the chain cannot fill: str.format's KeyError, ValueError, IndexError (and an attribute it cannot read)
    for bad, err in (("NFL|{season}", "KeyError"), ("NFL|2026}", "ValueError"), ("NFL|{0}", "IndexError"),
                     ("{today.x}|2026", "AttributeError")):
        lst.write_text(f"PL|2026/27\n{bad}\n")
        with pytest.raises((KeyError, ValueError, IndexError, AttributeError)) as ei:
            sp_run.resolve("weekly-fullseason", {}, cr.date(2026, 10, 25))
        assert str(ei.value).startswith(f"{lst} line 2: {bad!r} ") and err in str(ei.value)
        st = cr.fullseason_state(str(lst), cr.date(2026, 10, 22))
        assert st["state"] == "UNPARSEABLE" and st["entries"] == []
        assert st["why"] == f"{ei.value} (weekly-fullseason fails on this line too)"
    lst.write_text("PL|2026/27\nNFL|{season}\n")
    rc, t9, last = readout(no_settings, capsys)
    assert t9[1].startswith(f"    fullseason list: UNPARSEABLE → NOT-YET · {lst} line 2: 'NFL|{{season}}' ")
    assert t9[1].endswith("(weekly-fullseason fails on this line too)") and "KeyError" in t9[1]
    assert rc == 1 and "(T9) fullseason list UNPARSEABLE" in last


@pytest.mark.parametrize("line, which", [("|2026", "code"), ("NFL|", "season"), ("|", "code and season"),
                                         ("  |  2026 ", "code"), (" NFL |   ", "season")])
def test_t9_an_empty_code_or_season_is_unparseable_and_the_chain_refuses_it(no_settings, monkeypatch, capsys,
                                                                           line, which):
    """Law 4: a line whose code or season is empty once stripped names no competition. Before, it was counted
    ("N competitions", not binding) and the chain ran `sync-matches --competition  --season 2026`, a step bound to
    fail; now the chain refuses it at resolve, as it does a line without '|', and the readout reads UNPARSEABLE
    through the one parser."""
    lst = no_settings / "fullseason.list"
    lst.write_text(f"PL|2026/27\n{line}\n")
    monkeypatch.setenv("SP_FULLSEASON_LIST", str(lst))
    with pytest.raises(ValueError) as ei:
        sp_run.resolve("weekly-fullseason", {}, cr.date(2026, 10, 25))
    assert str(ei.value) == f"{lst} line 2: {line.strip()!r} is not CODE|SEASON (empty {which})"
    rc, t9, last = readout(no_settings, capsys)
    assert t9[1] == f"    fullseason list: UNPARSEABLE → NOT-YET · {ei.value} (weekly-fullseason fails on this line too)"
    assert rc == 1 and "(T9) fullseason list UNPARSEABLE" in last


def test_t9_a_half_str_format_leaves_empty_and_a_leading_bom(no_settings, monkeypatch, capsys):
    """The empty-half refusal holds after the chain's str.format too ("NFL|{today:.0}" formats to an empty season:
    before, the chain ran `--season ` and the readout counted "NFL|"), and a hand-edited file's leading UTF-8 BOM
    never rides into the first code (before: the readout printed an invisible "<BOM>MLB|2026" beside "MLB lines:
    none", and the chain ran `--competition <BOM>MLB`)."""
    lst = no_settings / "fullseason.list"
    monkeypatch.setenv("SP_FULLSEASON_LIST", str(lst))
    lst.write_text("PL|2026/27\nNFL|{today:.0}\n")
    with pytest.raises(ValueError) as ei:
        sp_run.resolve("weekly-fullseason", {}, cr.date(2026, 10, 25))
    assert str(ei.value) == f"{lst} line 2: 'NFL|{{today:.0}}' is not CODE|SEASON (empty season after str.format)"
    rc, t9, last = readout(no_settings, capsys)
    assert t9[1] == f"    fullseason list: UNPARSEABLE → NOT-YET · {ei.value} (weekly-fullseason fails on this line too)"
    assert rc == 1 and "(T9) fullseason list UNPARSEABLE" in last
    lst.write_bytes(b"\xef\xbb\xbfMLB|2026\nNFL|2026\n")
    steps = sp_run.resolve("weekly-fullseason", {}, cr.date(2026, 10, 25))
    assert [s[2] for s in steps] == ["MLB", "NFL"]
    st = cr.fullseason_state(str(lst), cr.date(2026, 10, 22))
    assert st["state"] == "ok" and st["entries"] == ["MLB|2026", "NFL|2026"]
    rc, t9, last = readout(no_settings, capsys)
    assert "\ufeff" not in "\n".join(t9) and st["mlb"] == ["MLB|2026"]
    assert any(ln.startswith("    ⚠ MLB line(s) listed: MLB|2026 ") for ln in t9)
    assert last.endswith(" · (T9) MLB line(s) on the list: MLB|2026")             # addendum 128 item 1(b): it binds


def test_t9_hosting_h1_query_writes_no_mlb_line():
    """hosting-h1.md T9's copy-paste query, run as written on a synthetic DB: every competition-season inside
    +-30 days EXCEPT MLB (ARCHITECT 2026-10-18, addendum 122 item 3(a): "writes every line EXCEPT MLB")."""
    import re
    import sqlite3
    doc = (ROOT / "docs" / "specs" / "hosting-h1.md").read_text()
    t9 = doc[doc.index("**T9. TERMINAL (host)"):doc.index("**T10. TERMINAL (host)")]
    sql = re.search(r'"(SELECT .*?;)"', t9, re.S).group(1)
    con = sqlite3.connect(":memory:")
    con.executescript("CREATE TABLE competitions (id INTEGER PRIMARY KEY, code TEXT);"
                      "CREATE TABLE matches (id INTEGER PRIMARY KEY, competition_id INTEGER, season TEXT,"
                      " utc_date TEXT);"
                      "INSERT INTO competitions VALUES (1, 'PL'), (2, 'NFL'), (3, 'MLB'), (4, 'MLB_SPRING'),"
                      " (5, 'NHL');")
    for cid, season, off in ((1, "2026/27", "+2 days"), (2, "2026", "-3 days"), (3, "2026", "+1 days"),
                             (4, "2026", "-5 days"), (5, "2026", "+90 days")):
        con.execute("INSERT INTO matches (competition_id, season, utc_date) VALUES (?, ?, datetime('now', ?))",
                    (cid, season, off))
    assert [r[0] for r in con.execute(sql)] == ["NFL|2026", "PL|2026/27"]


def test_t9_hosting_h1_block_installs_over_the_list_and_a_rerun_never_doubles(tmp_path):
    """#593 (ARCHITECT 2026-10-18, addendum 128 item 4: "the docs fix as proposed (write to a temp file, print,
    install over the list)"): hosting-h1.md T9's copy-paste block, run as written over the installed example, then
    run again (sqlite3, sudo and install stubbed on PATH; the DB and the list pointed into tmp_path; the temp file in
    TMPDIR=tmp_path). Before: `| sudo tee -a` kept the example's lines under the generated ones, and a second run wrote
    every line again, so the chain would sync each competition twice. After: each run prints the list and installs it
    over the file, which holds each line once, and the temp file is gone; the install's owner, group and mode are
    install.sh's own for that file (law 1: read, not assumed)."""
    import os
    import re
    import sqlite3
    import subprocess
    doc = (ROOT / "docs" / "specs" / "hosting-h1.md").read_text()
    t9 = doc[doc.index("**T9. TERMINAL (host)"):doc.index("**T10. TERMINAL (host)")]
    block = re.search(r"```\n(.*?)```", t9, re.S).group(1)
    db, lst, bin_ = tmp_path / "sports.db", tmp_path / "fullseason.list", tmp_path / "bin"
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE competitions (id INTEGER PRIMARY KEY, code TEXT);"
                      "CREATE TABLE matches (id INTEGER PRIMARY KEY, competition_id INTEGER, season TEXT,"
                      " utc_date TEXT);"
                      "INSERT INTO competitions VALUES (1, 'PL'), (2, 'NFL'), (3, 'MLB');"
                      "INSERT INTO matches (competition_id, season, utc_date) VALUES"
                      " (1, '2026/27', datetime('now', '+2 days')), (2, '2026', datetime('now', '-3 days')),"
                      " (3, '2026', datetime('now', '+1 days'));")
    con.commit()
    con.close()
    bin_.mkdir()
    stubs = {"sqlite3": (f"#!{sys.executable}\nimport sqlite3, sys\n"
                         "a = [x for x in sys.argv[1:] if x != '-readonly']\n"
                         "con = sqlite3.connect('file:' + a[0] + '?mode=ro', uri=True)\n"
                         "for r in con.execute(a[1]):\n    print('|'.join(map(str, r)))\n"),
             "sudo": '#!/bin/sh\nexec "$@"\n',
             "install": '#!/bin/sh\n# install [-o U -g G -m M] SRC DST: the copy over DST (no chown here)\n'
                        'for a in "$@"; do s=$d; d=$a; done\ncp "$s" "$d"\n'}
    for name, text in stubs.items():
        (bin_ / name).write_text(text)
        (bin_ / name).chmod(0o755)
    script = (block.replace("/opt/sports-predictor/data/sports.db", str(db))
              .replace("/etc/sports-predictor/fullseason.list", str(lst)))
    assert str(db) in script and str(lst) in script
    lst.write_text(EXAMPLE.read_text())                                # what install.sh puts there
    env = {**os.environ, "PATH": f"{bin_}{os.pathsep}{os.environ.get('PATH', '')}", "TMPDIR": str(tmp_path)}
    for _ in range(2):                                                 # the first run, then a re-run
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, env=env, timeout=60)
        assert r.returncode == 0, r.stderr
        assert r.stdout.splitlines() == ["NFL|2026", "PL|2026/27"]    # printed: the receipt
        assert lst.read_text().splitlines() == ["NFL|2026", "PL|2026/27"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bin", "fullseason.list", "sports.db"]
    assert "tee " not in block and block.count("/etc/sports-predictor/fullseason.list") == 1
    inst = [ln for ln in (ROOT / "deploy" / "hosting" / "install.sh").read_text().splitlines()
            if "etc/fullseason.list.example" in ln]
    flags = re.search(r" install (-o \S+ -g \S+ -m \d+) etc/fullseason\.list\.example ", inst[0]).group(1)
    assert len(inst) == 1 and f"sudo install {flags} " in block


def test_module_usage_names_every_option():
    """The module docstring's usage block names every option main() takes (the hidden --today aside)."""
    import re
    src = Path(cr.__file__).read_text()
    usage = cr.__doc__[:cr.__doc__.index("Prints, in order:")]
    opts = [o for o in re.findall(r'add_argument\("(--[a-z-]+)"', src) if o != "--today"]
    assert "--fullseason-list" in opts and [o for o in opts if f"[{o}" not in usage] == []


def test_t9_an_empty_fullseason_list_option_names_the_option(no_settings, monkeypatch, capsys):
    """An empty --fullseason-list overrides a set SP_FULLSEASON_LIST: NOT-YET, and the reason names the option, not
    the setting."""
    lst = no_settings / "fullseason.list"
    lst.write_text("PL|2026/27\n")
    monkeypatch.setenv("SP_FULLSEASON_LIST", str(lst))
    rc, t9, last = readout(no_settings, capsys, "--fullseason-list", "")
    assert t9[0] == "(T9) WEEKLY FULL-SEASON LIST — --fullseason-list: (empty path)"
    assert t9[1].startswith("    fullseason list: NOT SET → NOT-YET · --fullseason-list was given an empty path")
    assert "SP_FULLSEASON_LIST is not set" not in t9[1]
    assert rc == 1 and "(T9) fullseason list NOT SET" in last


def test_t9_an_mlb_line_on_the_list_binds_not_yet_with_the_line_named(no_settings, monkeypatch, capsys):
    """MLB is excluded from the host's list by ruling (addendum 122 item 3(a)). ARCHITECT 2026-10-18, addendum 128
    item 1(b): "AN MLB LINE ON THE HOST'S LIST BINDS: NOT-YET, with the line named. The ruling excluded MLB; a list
    that carries it is wrong, and a readout that prints a warning and says GO is softer than the rule." Before: the
    line printed with a ⚠ and nothing reached the unmet list. One condition: every MLB line, named, in the last line."""
    lst = no_settings / "fullseason.list"
    lst.write_text("NFL|2026\nMLB|2026\nmlb_spring|2026\nPL|2026/27\n")
    monkeypatch.setenv("SP_FULLSEASON_LIST", str(lst))
    rc, t9, last = readout(no_settings, capsys)
    assert t9[1] == "    fullseason list: 4 competitions — NFL|2026 · MLB|2026 · mlb_spring|2026 · PL|2026/27"
    assert t9[2] == ("    ⚠ MLB line(s) listed: MLB|2026, mlb_spring|2026 — MLB is excluded by ruling (addendum 122 "
                     "item 3(a)); an MLB line binds: NOT-YET (addendum 128 item 1(b))")
    assert rc == 1 and last.startswith("NOT-YET — ")
    assert last.endswith(" · (T9) MLB line(s) on the list: MLB|2026, mlb_spring|2026")
    assert [u for u in last.split(" · ") if u.startswith("(T9)")] == [
        "(T9) MLB line(s) on the list: MLB|2026, mlb_spring|2026"]      # the list itself is ok: only the MLB lines bind
    # every competition code the MLB adapter exposes reads as an MLB line; no other listed code does
    from src.adapters.mlb_stats_api import _COMPETITIONS
    assert _COMPETITIONS and all(cr.mlb_code(k) for k in _COMPETITIONS)
    assert not any(cr.mlb_code(k) for k in ("PL", "NFL", "NHL", "NCAA", "UEL", "CL", "ELC", "MLS", "MLBX"))


def test_t9_fullseason_list_option_reads_the_named_file(no_settings, monkeypatch, capsys):
    """Run away from the host (the laptop form, for the architect's dry reads only: ARCHITECT 2026-10-18, addendum 128
    item 1(a)): the host's file passed by name wins over the machine's setting, and the line names where it came
    from."""
    lst = no_settings / "host-fullseason.list"
    lst.write_text("PL|2026/27\nNFL|2026\n")
    monkeypatch.setenv("SP_FULLSEASON_LIST", str(EXAMPLE))
    rc, t9, last = readout(no_settings, capsys, "--fullseason-list", str(lst))
    assert t9[0] == f"(T9) WEEKLY FULL-SEASON LIST — --fullseason-list: {lst}"
    assert t9[1] == "    fullseason list: 2 competitions — PL|2026/27 · NFL|2026" and "(T9)" not in last


def test_the_runbook_runs_the_readout_on_the_host_and_labels_the_laptop_form():
    """ARCHITECT 2026-10-18, addendum 128 item 1(a), verbatim: "WHICH MACHINE RUNS `cutover-readiness`: the HOST, over
    ssh in the Thursday evening block, so (b) and (T9) read the host's own receipts and list; the laptop form
    (`--receipts FILE --fullseason-list FILE`) is for my dry reads only and is labelled as such on the page." The
    schedule's Thursday evening row and section 0's readout say so; addendum 113 item 5's quote stays verbatim."""
    rb = (ROOT / "docs" / "specs" / "h2-cutover-runbook.md").read_text()
    ruling = ("WHICH MACHINE RUNS `cutover-readiness`: the HOST, over ssh in the Thursday evening block, so (b) and (T9) "
              "read the host's own receipts and list; the laptop form (`--receipts FILE --fullseason-list FILE`) is for "
              "my dry reads only and is labelled as such on the page.")
    rows = [ln for ln in rb.splitlines() if ln.startswith("| Thu 10-22 evening |")]
    assert len(rows) == 1
    what, where = rows[0].split(" | ")[1:3]
    assert "on the HOST, over ssh in the Thursday evening block" in what and "on the laptop" not in what
    assert "for the architect's dry reads only" in where and "open question" not in where
    sched = rb[rb.index("## The 2026-10 schedule"):rb.index("## 0. Before the ruling day")]
    quoted = " ".join(" ".join(x[2:] for x in sched.splitlines() if x.startswith("> ")).split())
    assert "5. Thu 10-22 evening: `cli.py cutover-readiness` on the laptop; its GO / NOT-YET lines pasted to me." in quoted
    assert f"(a) {ruling}" in quoted
    sec0 = rb[rb.index("- **Readiness readout (#85"):rb.index("- **Host on a release tag.**")]
    assert ruling in " ".join(sec0.split())
    assert "- **The laptop form, for the architect's dry reads only** (addendum 128 item 1(a))" in sec0


def cli_row() -> str:
    rows = [ln for ln in (ROOT / "docs" / "CLI.md").read_text().splitlines() if ln.startswith("| `cutover-readiness` ")]
    assert len(rows) == 1
    return rows[0]


def test_the_host_readout_leaves_out_only_the_laptop_options_and_keeps_named():
    """Addendum 128 item 1(a) names the laptop form (`--receipts FILE --fullseason-list FILE`) as the architect's dry
    reads only; it says nothing about the host run's other options. A compare day that needs operator naming is named
    in the --named file (addendum 113 item 1, quoted on the runbook: "operator-named with evidence in the --named
    file"), on the host too. Before: the schedule's Thursday row, section 0 and docs/CLI.md told the operator to pass
    "no option" on the host, and docs/CLI.md credited that to 1(a)."""
    rb = (ROOT / "docs" / "specs" / "h2-cutover-runbook.md").read_text()
    rows = [ln for ln in rb.splitlines() if ln.startswith("| Thu 10-22 evening |")]
    sec0 = rb[rb.index("- **Readiness readout (#85"):rb.index("- **Host on a release tag.**")]
    host = "without `--receipts` or `--fullseason-list` (pass `--named FILE` when a day is operator-named)"
    assert len(rows) == 1
    for where in (rows[0], " ".join(sec0.split()), cli_row()):
        assert "no option" not in where and host in where


def test_t9_an_unparseable_list_is_not_yet_on_its_own_and_its_mlb_lines_are_named_once_it_parses(
        no_settings, monkeypatch, capsys):
    """The one parser (sp_run.fullseason_resolve) refuses the file at its first bad line, so a list that carries an
    MLB line and a line the chain cannot parse reads UNPARSEABLE, NOT-YET on its own, and names no MLB line: naming
    it would take a second parser, which fullseason_state rules out (whether it should is the architect's; the
    ledger entry asks). Once the list parses, the MLB line binds, named (addendum 128 item 1(b)). Before: the docs
    said an MLB line binds, named, with no word on a list that does not parse."""
    lst = no_settings / "fullseason.list"
    lst.write_text("MLB|2026\nNFL\n")
    monkeypatch.setenv("SP_FULLSEASON_LIST", str(lst))
    rc, t9, last = readout(no_settings, capsys)
    assert t9[1:] == [f"    fullseason list: UNPARSEABLE → NOT-YET · {lst} line 2: 'NFL' is not CODE|SEASON "
                      f"(weekly-fullseason fails on this line too)"]
    assert rc == 1 and last.endswith(" · (T9) fullseason list UNPARSEABLE") and "MLB" not in last
    lst.write_text("MLB|2026\nNFL|2026\n")                             # the parse fixed: the MLB line binds, named
    rc, t9, last = readout(no_settings, capsys)
    assert rc == 1 and last.endswith(" · (T9) MLB line(s) on the list: MLB|2026")
    rb = (ROOT / "docs" / "specs" / "h2-cutover-runbook.md").read_text()
    bullet = rb[rb.index("  - **(T9)** an ADDED binding condition"):rb.index("  - Last line: `GO — …`")]
    said = "MLB lines are named once the list parses: an UNPARSEABLE list is NOT-YET on its own"
    for doc in (cr.__doc__, bullet, cli_row()):
        assert said in " ".join(doc.split())


def test_the_runbook_t9_why_is_in_the_past_beside_the_run_once_bullet():
    """Addendum 128 item 4: "block_1018_t9_host.txt is NEVER re-run; today's one run wrote the 26 lines once". The
    T9 item's Why says what the host's file was until that run, dated, beside the Run-once bullet that records it.
    Before: it read "is still the installed example" and "step T9 was never run", one bullet above that record."""
    rb = (ROOT / "docs" / "specs" / "h2-cutover-runbook.md").read_text()
    t9 = rb[rb.index("- **T9: the weekly full-season list"):rb.index("- **Readiness readout (#85")]
    why = " ".join(t9[t9.index("  - Why: "):t9.index("  - TERMINAL (host), Tailscale:")].split())
    assert "is still the installed example" not in why and "was never run" not in why
    assert why.startswith("- Why: until 10-18 `/etc/sports-predictor/fullseason.list` on the host was the installed "
                          "example (comment lines only)")
    assert "block_1018_t9_host.txt's one run on 10-18 wrote its 26 lines (addendum 128 item 4)" in why
    assert "  - Run once: the block is NEVER re-run (ARCHITECT 2026-10-18, addendum 128 item 4" in t9
