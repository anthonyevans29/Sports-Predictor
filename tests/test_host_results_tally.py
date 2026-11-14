"""THE HOST'S RESULTS-TALLY EXPORT (ARCHITECT 2026-11-08 07:50 ET, addendum 289 item 3, verbatim: "results-tally's
RESULTS.md and its JSON written on the HOST by the morning-after chain and mirrored, so the compare morning reads one
tally per machine (the laptop's is regenerated; the host's is the record of production) — read-only on the DB, a file
under exports/, the mirror's top-level rule carries it"; addendum 230 item 2(b) and 248 item 2(c): "results-tally on the
host (DB mode=ro) as the last step of soccer-morning-after, its RESULTS.md and a JSON beside it to the mirror as a kind
of its own"; #875).

Pinned here: the chain's step (soccer-morning-after's last; mlb-morning's H0-9 tally unchanged), the two paths under
exports/ and never ./RESULTS.md, every section's read through mode=ro (a write refused by SQLite, the bindings restored,
a missing DB refused with nothing written), the JSON's shape (the file's sections in order, their lines verbatim, the
figures their computation returned, the per-row lists left out or counted, strict JSON), no forbidden content (no order text,
contract count, unit fraction, pool, account id or dollar figure, whatever the closing files carry), the command's host
fence, the laptop's tally byte for byte, the mirror's plan copying both files under their own kinds, and the compare
left as it is (the JSON one more `only on host` line; how the compare classes it is an open item for the architect)."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

from tests.test_exec_cohorts import LATE, _match, desk, row
from tests.test_record_vs_close import iso_db  # noqa: F401  (a fixture: a throwaway SQLite, cwd = tmp_path)
from tests.test_void_redated import _mlb_world, write_closing
from tests.test_hosting_pack import receipts, sandbox  # noqa: E402,F401  (the sp_run sandbox: tmp receipts/lock)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))
import chains  # noqa: E402
import compare_exports as ce  # noqa: E402
import exports_mirror as em  # noqa: E402

pytestmark = pytest.mark.usefixtures("iso_db")

ACCOUNT = "ACCT-ZZ-0000"                         # a synthetic account id: never in either file
ORDER_TEXT = "BUY YES 99 @ 41c ORDER-TEXT-MARK"  # a synthetic order line: never in either file
FORBIDDEN_KEYS = {"order", "contracts", "fee_order_contracts", "pool", "pool_usd", "fraction", "half_fraction",
                  "account", "account_id", "desk_meta", "text"}


def _world(tmp_path):
    """MLB graded games (the MLB section's figures) and a closing file whose PLAY rows carry every field the mirror
    must never get from the tally: an order block with its text and contracts, the unit's fraction, the pool, an
    account id."""
    _mlb_world()                                   # its MLB competition holds the two games below too
    _match(1901, "MLB", "HX1", "AX1", hs=5, aw=2)
    _match(1902, "MLB", "HX2", "AX2", hs=1, aw=4)
    ex = tmp_path / "exports"
    rows = []
    for mid, h, a in ((1901, "HX1", "AX1"), (1902, "HX2", "AX2")):
        d = desk(edge=2.0)
        d["order"] = {"unit": 0.5, "text": ORDER_TEXT, "contracts": 99}
        d["exec"]["contracts"] = 99
        d["fee_order_contracts"] = 99
        r = row(mid, h, a, d)
        r["desk_meta"] = {"unit": {"fraction": 0.08, "half_fraction": 0.04, "pool_usd": 12345.0},
                          "account_id": ACCOUNT}
        rows.append(r)
    write_closing(ex, LATE, rows)
    return ex


def _walk_keys(v):
    if isinstance(v, dict):
        for k, x in v.items():
            yield k
            yield from _walk_keys(x)
    elif isinstance(v, list):
        for x in v:
            yield from _walk_keys(x)


def _strings(v):
    if isinstance(v, dict):
        for k, x in v.items():
            yield str(k)
            yield from _strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from _strings(x)
    elif isinstance(v, str):
        yield v


# ---- the chain ----------------------------------------------------------------------------------------------------

def test_the_host_tally_is_the_last_step_of_soccer_morning_after_and_of_no_other_chain():
    steps = chains.CHAINS["soccer-morning-after"]["steps"]
    assert chains.HOST_TALLY_STEP == ["results-tally", "--host-export"]
    assert steps[-1] == chains.HOST_TALLY_STEP and steps.count(chains.HOST_TALLY_STEP) == 1
    assert steps[-2] == chains.SHADOW_EXPORT_STEP                      # 185 D2: still after every sync
    assert all(s[0].startswith("sync-") for s in steps[:-4]) and steps[-4][0] == "evaluate"
    holders = sorted(n for n, ch in chains.CHAINS.items() if chains.HOST_TALLY_STEP in (ch.get("steps") or []))
    assert holders == ["soccer-morning-after"]
    assert chains.CHAINS["soccer-morning-after"]["backup"] == "daily"
    assert "results-tally" in chains.UNMETERED                         # it reads the DB only
    # H0-9 unchanged: mlb-morning still ends on the bare tally (the repo's RESULTS.md, which sp_deploy restores)
    assert chains.CHAINS["mlb-morning"]["steps"][-1] == ["results-tally"]
    assert sum(1 for ch in chains.CHAINS.values() for s in ch.get("steps") or [] if s == ["results-tally"]) == 1


def test_a_refused_shadow_export_does_not_stop_the_tally(sandbox):
    """Addendum 294 item A.3: the chain's go_on names the shadow export, with its own reason; a D7 refusal (exit 2) is
    receipted, the tally still runs, and the chain's exit stays the refusal's (OnFailure pages). Without the go_on the
    same refusal stops the chain before the tally (the control)."""
    ch = chains.CHAINS["soccer-morning-after"]
    assert ch["go_on"] == ("export-soccer-expansion-shadow",) and ch["go_on_why"] == chains.SHADOW_GO_ON
    assert chains.SHADOW_GO_ON.startswith("addendum 294 item A.3: ")
    assert not ch.get("continue_on_sync_failure")                                  # not the wider flag
    import datetime as _dt

    import sp_common as c
    import sp_run
    (c.REPO / "cli.py").write_text(
        "import sys\nprint('ran', ' '.join(sys.argv[1:]))\n"
        "sys.exit(2 if sys.argv[1] == 'export-soccer-expansion-shadow' else 0)\n")
    steps = [chains.SHADOW_EXPORT_STEP, chains.HOST_TALLY_STEP]
    day = _dt.date(2026, 11, 8)
    rep = {}
    rc, ok = sp_run.run_steps(steps, "t", "u", "r1", day, sp_run.new_quota(), report=rep,
                              go_on=ch["go_on"], go_on_why=ch["go_on_why"])
    assert (rc, ok, rep["stopped_at"]) == (2, 1, None)                             # the tally ran; exit the refusal's
    got = [r for r in receipts(sandbox) if r.get("run_id") == "r1" and r["kind"] == "step"]
    assert [r["command"].split()[2] for r in got] == ["export-soccer-expansion-shadow", "results-tally"]
    assert got[0]["exit"] == 2 and got[0]["continued"] == chains.SHADOW_GO_ON and got[1]["exit"] == 0
    rep = {}                                                                       # the control: no go_on
    rc, ok = sp_run.run_steps(steps, "t", "u", "r2", day, sp_run.new_quota(), report=rep)
    assert (rc, ok, rep["stopped_at"]) == (2, 0, 1)


def test_the_flag_is_a_real_option_of_the_command():
    import cli
    opts = {o for p in cli.cli.commands["results-tally"].params for o in p.opts}
    assert {"--days", "--host-export"} <= opts


# ---- the paths, the read-only DB ------------------------------------------------------------------------------------

def test_the_export_writes_its_two_files_under_exports_and_never_the_repos_results_md(tmp_path):
    from src.walters.export import host_results_tally
    ex = _world(tmp_path)
    md, js = host_results_tally(days=36500)
    assert (md, js) == ("exports/RESULTS.md", "exports/results_tally.json")
    assert (tmp_path / md).is_file() and (tmp_path / js).is_file()
    assert not (tmp_path / "RESULTS.md").exists()                      # the repo's RESULTS.md is never written
    assert sorted(p.name for p in ex.iterdir() if p.name.startswith(".") or ".tmp" in p.name) == []   # none left
    txt = (tmp_path / md).read_text()
    assert txt.startswith("# Results — rolling 36500 days")
    assert "THE HOST'S TALLY (ARCHITECT 2026-11-08, addendum 289 item 3)" in txt
    assert "rebuilt from the laptop's DB" not in txt


def test_the_temporary_names_are_hidden_from_the_laptops_pull_and_the_mirror(tmp_path, monkeypatch):
    """The verifier's nit on the first build (`RESULTS.md.tmp-<pid>` matched pull_exports.SAFE_NAME): each file is
    written under a dot-led name (coverage_map.write_document's form) and renamed into place."""
    import os

    import pull_exports
    from src.walters.export import host_results_tally
    _world(tmp_path)
    moved = []
    real = os.replace
    monkeypatch.setattr(os, "replace", lambda a, b: (moved.append((os.path.basename(a), os.path.basename(b))),
                                                     real(a, b))[1])
    host_results_tally(days=36500)
    assert [b for _, b in moved] == ["RESULTS.md", "results_tally.json"]
    for a, _ in moved:
        assert a.startswith(".") and a.endswith(".tmp") and not pull_exports.SAFE_NAME.match(a), a
        assert not a.endswith(em.SUFFIXES)


def test_every_section_reads_through_mode_ro_and_the_bindings_are_restored(tmp_path, monkeypatch):
    """A section that tries to write (here: the exec cohorts' session) is refused by SQLite itself; the section prints
    "Grade unavailable." and the JSON says so; the database file is unchanged; the module's engine and SessionLocal are
    the ones from before the run."""
    from sqlalchemy import text

    from src.db import database
    from src.walters import exec_cohorts as xc
    from src.walters.export import host_results_tally
    _world(tmp_path)
    db = tmp_path / "iso.db"
    before = (hashlib.sha256(db.read_bytes()).hexdigest(), db.stat().st_mtime_ns)
    seen = {}

    def writing_tally(exports_dir, registry_path=None):
        seen["url"] = str(database.SessionLocal.kw["bind"].url)
        try:
            with database.session_scope() as s:
                s.execute(text("CREATE TABLE should_not_exist (x INTEGER)"))
        except Exception as e:                       # noqa: BLE001
            seen["error"] = str(e)
            raise
    monkeypatch.setattr(xc, "tally", writing_tally)
    engine, sl = database._engine, database.SessionLocal
    _, js = host_results_tally(days=36500)
    assert "mode=ro" in seen["url"]
    assert "readonly" in seen["error"].lower()
    assert (database._engine, database.SessionLocal) == (engine, sl)
    assert (hashlib.sha256(db.read_bytes()).hexdigest(), db.stat().st_mtime_ns) == before
    doc = json.loads((tmp_path / js).read_text())
    sec = [s for s in doc["sections"] if s["title"].startswith("EXEC COHORTS")]
    assert len(sec) == 1 and sec[0]["unavailable"] is True and sec[0]["figures"] is None
    assert sec[0]["lines"] == ["Grade unavailable."]


def test_a_missing_db_is_refused_and_neither_file_is_written(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from src.db import database
    from src.walters.export import host_results_tally
    gone = tmp_path / "nowhere" / "absent.db"
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=create_engine(f"sqlite:///{gone}")))
    with pytest.raises(database.ReadOnlyRefused):
        host_results_tally(days=30)
    assert not gone.exists() and not gone.parent.exists()              # never created
    assert not (tmp_path / "exports" / "RESULTS.md").exists()
    assert not (tmp_path / "exports" / "results_tally.json").exists()


def test_a_missing_db_creates_no_export_folder(tmp_path, monkeypatch):
    # Codex on #880 (4506541720): the refusal is checked BEFORE the export folder is made, so a missing database
    # leaves the filesystem untouched, the folder included
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from src.db import database
    from src.walters.export import host_results_tally
    gone = tmp_path / "nowhere" / "absent.db"
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=create_engine(f"sqlite:///{gone}")))
    out = tmp_path / "fresh" / "exports"
    with pytest.raises(database.ReadOnlyRefused):
        host_results_tally(days=30, out_dir=str(out))
    assert not out.exists() and not out.parent.exists()


# ---- the JSON -------------------------------------------------------------------------------------------------------

def test_the_json_is_the_files_sections_in_order_with_their_lines_and_figures(tmp_path):
    from src.walters.export import host_results_tally
    _world(tmp_path)
    md, js = host_results_tally(days=36500)
    txt = (tmp_path / md).read_text()
    raw = (tmp_path / js).read_text()
    doc = json.loads(raw, parse_constant=lambda c: pytest.fail(f"non-strict JSON constant {c}"))
    assert doc["kind"] == "results_tally_v1" and doc["machine"] == "host" and doc["markdown"] == "RESULTS.md"
    assert doc["days"] == 36500 and doc["exported_at"].endswith("Z") and "git_sha" in doc
    assert set(doc) == {"kind", "exported_at", "git_sha", "machine", "days", "markdown", "database", "closing_files",
                        "note", "sections", "console"}
    assert "predictions" not in doc                                    # window.canonical_models skips it
    heads = [ln[3:].strip() for ln in txt.splitlines() if ln.startswith("## ")]
    assert [s["title"] for s in doc["sections"]] == heads
    for s in doc["sections"]:
        assert set(s) == {"title", "lines", "figures", "unavailable"}
        for ln in s["lines"]:
            assert ln in txt.splitlines(), ln                          # verbatim: never a line the file lacks
    mlb = doc["sections"][0]
    assert mlb["title"] == "MLB" and mlb["unavailable"] is False
    f = mlb["figures"]
    assert f["games"] == 2 and f["hits"] == 2 and "- Sides: **2/2** (100.0%)" in mlb["lines"]
    assert f["vs_close"]["games"] == 2 and set(f["vs_close"]) >= {"model_log_loss", "close_log_loss", "ci95"}
    assert f"- Mean log-loss: {f['mean_log_loss']:.4f} (n={f['log_loss_n']})" in mlb["lines"]
    ex = [s for s in doc["sections"] if s["title"].startswith("EXEC COHORTS")][0]["figures"]
    assert ex["files"] == 1 and ex["cells"]["MLB"]["0 < exec < 4"]["plays"] == 2
    assert doc["console"][0].startswith("close capture age")
    assert not {"lines", "rows"} & set(_walk_keys([s["figures"] for s in doc["sections"]]))


def test_the_nhl_shadows_record_against_the_close_reaches_the_json_and_its_per_call_lines_do_not(tmp_path,
                                                                                                    monkeypatch):
    """230 item 2(b): "with it the NHL shadow's record against the close reaches the mirror". The section prints
    grade()'s figures, graded once; the JSON carries them, its per-call `lines` (team names, probabilities) left out."""
    from src.walters import nhl_shadow as sh
    from src.walters.export import host_results_tally
    from src.walters.vs_close import block
    calls = []
    canned = {"graded": 2, "priced": 2, "unpriced": 0, "no_fit": 0, "not_v7": 0, "undecided": 0, "fallback": 0,
              "fallback_priced": 0, "fallback_unpriced": 0, "fallback_mean_clv_pp": None, "fallback_value_side_n": 0,
              "fallback_unanchored": 0, "fallback_mean_value_side_clv_pp": None,
              "graded_by_name": {sh.MODEL_VERSION: 2, sh.FALLBACK_VERSION: 0,
                                 f"{sh.REFERENCE_VERSION} (reference line only)": 0},
              "mean_clv_pp": 1.25, "value_side_n": 0, "unanchored": 2, "mean_value_side_clv_pp": None,
              "calls_on_file": 2, "lines": ["  SECRET-LINE A @ B v7_H=0.612"], "reference_priced": 2,
              "reference_mean_clv_pp": -0.5,
              "vs_close": {sh.MODEL_VERSION: block([(0.6, 0.55), (0.4, 0.45)]), sh.FALLBACK_VERSION: block([]),
                           sh.REFERENCE_VERSION: block([(0.58, 0.55), (0.42, 0.45)])}}

    def fake_grade(days=30, export_dir="exports", now=None, progress=None):
        calls.append(days)
        return canned
    monkeypatch.setattr(sh, "grade", fake_grade)
    _, js = host_results_tally(days=30)
    assert calls == [30]                                               # graded once, for the file and the JSON
    doc = json.loads((tmp_path / js).read_text())
    nhl = [s for s in doc["sections"] if s["title"].startswith("NHL — REFERENCE MODEL")][0]
    assert nhl["figures"]["vs_close"] == json.loads(json.dumps(canned["vs_close"]))
    assert "lines" not in nhl["figures"] and "SECRET-LINE" not in json.dumps(doc)
    assert any(ln.startswith(f"  - {sh.MODEL_VERSION}: vs close") for ln in nhl["lines"])


ALLOWED_LISTS = {"ci95", "families", "certification"}     # a pair, the family names, the head's (status, id)


def _lists(v, key=None):
    if isinstance(v, dict):
        for k, x in v.items():
            yield from _lists(x, k)
    elif isinstance(v, list):
        yield key, v
        for x in v:
            yield from _lists(x, key)


def test_the_figures_carry_no_per_row_list_only_its_count(tmp_path):
    """The verifier's finding on the first build: `runs` (one stamp per PLAY row), `ladder_edges` (each LADDER row's
    exec edge), the void labels and the close record's per-game quality rows reached the JSON as lists. Each is now its
    count; the per-call `lines` and per-game `rows` stay left out; any other list of dicts is counted by its shape."""
    from src.walters.export import _tally_jsonable, host_results_tally
    _world(tmp_path)
    _, js = host_results_tally(days=36500)
    doc = json.loads((tmp_path / js).read_text())
    bad = [(s["title"], k, v) for s in doc["sections"] for k, v in _lists(s["figures"]) if k not in ALLOWED_LISTS]
    assert bad == [], bad
    ex = [s for s in doc["sections"] if s["title"].startswith("EXEC COHORTS")][0]["figures"]
    assert ex["runs"] == 2 and ex["unreadable"] == 0                   # two PLAY rows: their count, not their stamps
    assert ex["left_out"]["MLB"]["ladder_edges"] == 0 and ex["left_out"]["MLB"]["void"] == 0
    assert doc["sections"][0]["figures"]["void"] == 0                  # MLB: the void labels' count
    got = _tally_jsonable({"runs": ["a", "b"], "ladder_edges": [1.5, 2.5, 3.5], "void": ["match 1 A @ B: x"],
                           "redated": [], "redated_rows": ["match 2 C @ D: y"], "unreadable": ["f.json"],
                           "quality": {"stale": [{"match_id": 1}], "superseded": [{"match_id": 2}, {"match_id": 3}]},
                           "other": [{"match_id": 4}], "lines": ["  A @ B 0.6"], "rows": [{"match_id": 5}],
                           "families": ["MLB", "NFL"], "ci95": (0.1, 0.2), "void_n": 3, "w": 1})
    assert got == {"runs": 2, "ladder_edges": 3, "void": 1, "redated": 0, "redated_rows": 1, "unreadable": 1,
                   "quality": {"stale": 1, "superseded": 2}, "other": 1, "families": ["MLB", "NFL"],
                   "ci95": [0.1, 0.2], "void_n": 3, "w": 1}


def test_neither_file_carries_an_order_a_contract_count_a_unit_fraction_the_pool_an_account_or_a_dollar(tmp_path):
    from src.walters.export import host_results_tally
    _world(tmp_path)
    md, js = host_results_tally(days=36500)
    txt, raw = (tmp_path / md).read_text(), (tmp_path / js).read_text()
    doc = json.loads(raw)
    assert not FORBIDDEN_KEYS & set(_walk_keys(doc))
    for blob in (txt, *_strings(doc)):
        assert "$" not in blob and ACCOUNT not in blob and "ORDER-TEXT-MARK" not in blob
        assert "12345" not in blob and "contracts" not in blob.lower()


# ---- the command --------------------------------------------------------------------------------------------------

def test_the_command_refuses_off_the_host_and_writes_nothing(tmp_path):
    import cli
    _world(tmp_path)
    r = CliRunner().invoke(cli.cli, ["results-tally", "--host-export"])      # conftest pins the role to laptop
    assert r.exit_code == 2, r.output
    assert "REFUSED: results-tally --host-export runs on the host only" in r.output
    assert "this machine's role is laptop" in r.output
    assert not (tmp_path / "exports" / "RESULTS.md").exists()
    assert not (tmp_path / "exports" / "results_tally.json").exists() and not (tmp_path / "RESULTS.md").exists()


def test_the_command_writes_both_files_on_the_host(tmp_path, monkeypatch):
    import cli
    _world(tmp_path)
    monkeypatch.setenv("SP_EXPORTS_MIRROR_ROLE", "host")
    r = CliRunner().invoke(cli.cli, ["results-tally", "--host-export", "--days", "36500"])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "exports" / "RESULTS.md").is_file() and (tmp_path / "exports" / "results_tally.json").is_file()
    assert not (tmp_path / "RESULTS.md").exists()
    assert "close capture age" in r.output                             # the console lines, as the bare command's


def test_the_laptops_tally_is_byte_for_byte_what_it_was_and_the_hosts_differs_only_by_its_header_line(tmp_path):
    from src.walters.export import host_results_tally, results_tally
    _world(tmp_path)
    a, b = tmp_path / "A.md", tmp_path / "B.md"
    results_tally(days=36500, out_path=str(a))
    got: dict = {}
    results_tally(days=36500, out_path=str(b), collect=got)
    strip = lambda t: "\n".join(x for x in t.splitlines() if "Auto-generated" not in x)  # noqa: E731  (the clock)
    assert strip(a.read_text()) == strip(b.read_text())                 # collect changes nothing in the file
    assert "_REGENERATED, NOT AUTHORITATIVE IN GIT (ruling 2026-10-01): this file is rebuilt from the laptop's DB" \
        in a.read_text()
    md, _ = host_results_tally(days=36500)
    la, ho = strip(a.read_text()).splitlines(), strip((tmp_path / md).read_text()).splitlines()
    assert len(la) == len(ho)
    differ = [(x, y) for x, y in zip(la, ho) if x != y]
    assert len(differ) == 1 and differ[0][0].startswith("_REGENERATED") and differ[0][1].startswith("_THE HOST'S")


# ---- the mirror and the compare -------------------------------------------------------------------------------------

def test_the_mirrors_top_level_rule_carries_both_files_under_their_own_kinds():
    today = date(2026, 11, 9)
    mt = datetime(2026, 11, 9, 9, 58, tzinfo=timezone.utc).timestamp()
    assert (em.kind_of("RESULTS.md"), em.kind_of("results_tally.json")) == ("RESULTS", "results_tally")
    p = em.plan([("RESULTS.md", mt), ("results_tally.json", mt), ("coverage_2026-11-09.json", mt)], "host", today)
    assert p["dated"]["host/2026-11-09/RESULTS.md"] == "RESULTS.md"
    assert p["dated"]["host/2026-11-09/results_tally.json"] == "results_tally.json"
    assert p["latest"]["host/latest/RESULTS.md"] == "RESULTS.md"
    assert p["latest"]["host/latest/results_tally.json"] == "results_tally.json"
    # the same stem would be ONE kind, and latest/ keeps one file per kind: why the JSON is not RESULTS.json
    one = em.plan([("RESULTS.md", mt), ("RESULTS.json", mt + 1)], "host", today)["latest"]
    assert list(one) == ["host/latest/RESULTS.json"]


def _cmp(tmp_path, laptop: dict, host: dict) -> subprocess.CompletedProcess:
    la, ho = tmp_path / "laptop" / "2026-11-09", tmp_path / "host" / "2026-11-09"
    for d, files in ((la, laptop), (ho, host)):
        d.mkdir(parents=True, exist_ok=True)
        for name, doc in files.items():
            (d / name).write_text(doc if isinstance(doc, str) else json.dumps(doc))
    env = {"PATH": "/usr/bin:/bin"}
    return subprocess.run([sys.executable, str(ROOT / "deploy" / "hosting" / "compare_exports.py"), str(la), str(ho),
                           "--since", "0"], capture_output=True, text=True, env=env)


FIX = {"fixtures_NHL_2026-11-09.json": {"git_sha": "abc", "fixtures": [{"home_team": "H", "away_team": "A",
                                                                         "utc_date": "2026-11-09T23:00:00"}]}}


def test_the_compare_reads_the_hosts_tally_as_any_host_only_kind(tmp_path):
    """The host's tally is one more `only on host` line, as the host's nhl_shadow file is. The open item this test
    pinned is RULED (ARCHITECT 2026-11-11, addendum 335 item 4(c), verbatim): "a kind not on it is EXPECTED ONE-SIDED
    (coverage, the window card, the UNL and league shadows, closings, slates, the MLB results file), printed and
    counted, never a cause of DIVERGENT". So beside the paired fixtures_NHL pair (identical, rows in the window) the
    day reads CLEAN, the tally and the shadow listed as expected one-sided."""
    tally = {"kind": "results_tally_v1", "sections": [{"title": "MLB", "lines": ["- Sides: **1/2**"]}]}
    shadow = {"calls": []}
    r = _cmp(tmp_path, dict(FIX), {**FIX, "results_tally.json": tally, "nhl_shadow_2026-11-09_1601.json": shadow,
                                   "RESULTS.md": "# Results"})
    out = r.stdout.splitlines()
    assert r.returncode == 0 and "VERDICT: CLEAN" in out, r.stdout
    assert "· results_tally.json: only on host (expected one-sided: results_tally is not a paired kind)" in out
    assert "· nhl_shadow_2026-11-09_1601.json: only on host (expected one-sided: nhl_shadow is not a paired kind)" in out
    assert "machine-state files: coverage laptop no / host no" in out
    assert ce.MACHINE_STATE_KINDS == ("coverage",) and ce.machine_state_kind("results_tally.json") is None
    assert not hasattr(ce, "TALLY_KINDS") and not hasattr(ce, "tally_line")


def test_the_window_card_never_reads_the_tally(tmp_path):
    from src.walters.export import host_results_tally
    from src.walters.window import canonical_models
    _world(tmp_path)
    host_results_tally(days=36500)
    assert canonical_models(tmp_path / "exports") == {}


def test_an_empty_machine_still_writes_both_files_with_every_section(tmp_path):
    """An empty machine (no game, no closing file): both files, every section present, none unavailable."""
    from src.walters.export import host_results_tally
    _, js = host_results_tally(days=30)
    doc = json.loads((tmp_path / js).read_text())
    assert [s["title"].split(" ")[0] for s in doc["sections"]][:3] == ["MLB", "Soccer", "NFL"]
    assert not any(s["unavailable"] for s in doc["sections"])


# ---- #881 (ARCHITECT 2026-11-14 13:38 ET, addendum 382 item 6(iv)): the tally pair all-or-nothing; the shadow
# grades read the requested exports_dir -------------------------------------------------------------------------------

def test_881_a_failed_json_rename_leaves_the_previous_pair_as_it_was(tmp_path, monkeypatch):
    """#881 item 1 (Codex on #880, 4506565251): the Markdown is renamed into place, then the JSON; if the JSON's rename
    fails, the new Markdown must not sit beside the old JSON (sp_run mirrors even after a non-zero exit). The pair is
    published all-or-nothing: the previous RESULTS.md is put back, the error raised, no temporary file left. Fail-first:
    on main the new RESULTS.md stayed beside the old results_tally.json."""
    import os

    from src.walters.export import host_results_tally
    ex = _world(tmp_path)
    host_results_tally(days=36500)
    old_md, old_js = (ex / "RESULTS.md").read_bytes(), (ex / "results_tally.json").read_bytes()
    real = os.replace

    def json_fails(a, b):
        if os.path.basename(b) == "results_tally.json":
            raise OSError(28, "No space left on device")
        return real(a, b)
    monkeypatch.setattr(os, "replace", json_fails)
    monkeypatch.setattr("src.walters.export.utc_now_naive", lambda: datetime(2031, 1, 1))   # a different stamp
    with pytest.raises(OSError):
        host_results_tally(days=36499)                                 # a different header: the new MD differs
    assert (ex / "RESULTS.md").read_bytes() == old_md and (ex / "results_tally.json").read_bytes() == old_js
    assert sorted(p.name for p in ex.iterdir() if p.name.startswith(".")) == []


def test_881_a_failed_json_rename_on_a_first_export_leaves_neither_file(tmp_path, monkeypatch):
    """The same failure with no previous pair: neither file is left (never a Markdown with no JSON)."""
    import os

    from src.walters.export import host_results_tally
    ex = _world(tmp_path)
    real = os.replace

    def json_fails(a, b):
        if os.path.basename(b) == "results_tally.json":
            raise OSError(28, "No space left on device")
        return real(a, b)
    monkeypatch.setattr(os, "replace", json_fails)
    with pytest.raises(OSError):
        host_results_tally(days=36500)
    assert not (ex / "RESULTS.md").exists() and not (ex / "results_tally.json").exists()
    assert sorted(p.name for p in ex.iterdir() if p.name.startswith(".")) == []


def test_881_the_nhl_and_unl_shadow_grades_read_the_requested_exports_dir(tmp_path, monkeypatch):
    """#881 item 2 (Codex on #880, 4506565254): results_tally's NHL and UNL sections called grade() without
    export_dir, so a non-default exports_dir mixed two export sets in one file. Both now pass the caller's directory.
    Fail-first: on main both read "exports"."""
    from src.walters import intl_shadow, nhl_shadow
    from src.walters.export import results_tally
    _world(tmp_path)
    seen = {}

    def spy(name, real):
        def grade(days=30, export_dir="exports", now=None, progress=None):
            seen[name] = export_dir
            return real(days=days, export_dir=export_dir, now=now, progress=progress)
        return grade
    monkeypatch.setattr(nhl_shadow, "grade", spy("nhl", nhl_shadow.grade))
    monkeypatch.setattr(intl_shadow, "grade", spy("unl", intl_shadow.grade))
    other = tmp_path / "other_exports"
    other.mkdir()
    results_tally(days=36500, out_path=str(tmp_path / "R.md"), exports_dir=str(other))
    assert seen == {"nhl": str(other), "unl": str(other)}, seen


def test_881_with_no_hard_links_the_previous_markdown_is_held_by_a_copy(tmp_path, monkeypatch):
    """A filesystem that refuses os.link (EPERM, some mounts) holds the previous RESULTS.md by a copy: the export never
    fails where it succeeded before #881, and a failed JSON rename still puts the previous pair back."""
    import os

    from src.walters.export import host_results_tally
    ex = _world(tmp_path)
    host_results_tally(days=36500)
    old_md = (ex / "RESULTS.md").read_bytes()

    def no_link(a, b):
        raise PermissionError(1, "Operation not permitted")
    monkeypatch.setattr(os, "link", no_link)
    md, js = host_results_tally(days=36499)                             # succeeds: the copy held the old Markdown
    assert (tmp_path / md).read_bytes() != old_md and (tmp_path / js).is_file()
    real = os.replace
    monkeypatch.setattr(os, "replace", lambda a, b: (_ for _ in ()).throw(OSError(28, "No space left on device"))
                        if os.path.basename(b) == "results_tally.json" else real(a, b))
    newer = (ex / "RESULTS.md").read_bytes()
    with pytest.raises(OSError):
        host_results_tally(days=36498)
    assert (ex / "RESULTS.md").read_bytes() == newer
    assert sorted(p.name for p in ex.iterdir() if p.name.startswith(".")) == []


def _interrupt_after(target: str, monkeypatch):
    """os.replace does the real rename, then a KeyboardInterrupt (as CPython delivers SIGINT once the call returns)."""
    import os
    real = os.replace

    def replace(a, b):
        real(a, b)
        if os.path.basename(b) == target:
            raise KeyboardInterrupt
    monkeypatch.setattr(os, "replace", replace)


def test_881_review_an_interrupt_after_the_markdown_rename_puts_the_previous_pair_back(tmp_path, monkeypatch):
    """Review of #881: an interrupt arriving after the Markdown's rename (outside the old guard) left the new RESULTS.md
    beside the old JSON. The state is read from the filesystem: the Markdown swapped, the JSON not, so it is put back."""
    from src.walters.export import host_results_tally
    ex = _world(tmp_path)
    host_results_tally(days=36500)
    old = (ex / "RESULTS.md").read_bytes(), (ex / "results_tally.json").read_bytes()
    _interrupt_after("RESULTS.md", monkeypatch)
    with pytest.raises(KeyboardInterrupt):
        host_results_tally(days=36499)
    assert ((ex / "RESULTS.md").read_bytes(), (ex / "results_tally.json").read_bytes()) == old
    assert sorted(p.name for p in ex.iterdir() if p.name.startswith(".")) == []


def test_881_review_an_interrupt_after_the_json_rename_leaves_the_new_pair_complete(tmp_path, monkeypatch):
    """Review of #881: an interrupt after the JSON's rename means both are in place: the pair is new and whole, and the
    previous Markdown must NOT be put back beside the new JSON."""
    import json as _json

    from src.walters.export import host_results_tally
    ex = _world(tmp_path)
    host_results_tally(days=36500)
    _interrupt_after("results_tally.json", monkeypatch)
    with pytest.raises(KeyboardInterrupt):
        host_results_tally(days=36499)
    assert (ex / "RESULTS.md").read_text().startswith("# Results — rolling 36499 days")
    assert _json.loads((ex / "results_tally.json").read_text())["days"] == 36499
    assert sorted(p.name for p in ex.iterdir() if p.name.startswith(".")) == []


def test_881_review_a_failed_rollback_keeps_the_previous_markdown_and_no_new_one_beside_the_old_json(tmp_path,
                                                                                                    monkeypatch):
    """Review of #881: when the rollback rename itself fails, the previous Markdown's only copy is KEPT (its hidden
    name, given in the error) and the new Markdown is removed: never a new Markdown beside the old JSON, never the
    previous Markdown destroyed. The JSON's own error is the one raised."""
    import os

    from src.walters.export import host_results_tally
    ex = _world(tmp_path)
    host_results_tally(days=36500)
    old_md, old_js = (ex / "RESULTS.md").read_bytes(), (ex / "results_tally.json").read_bytes()
    real = os.replace

    def replace(a, b):
        if os.path.basename(b) == "results_tally.json":
            raise OSError(28, "No space left on device")
        if ".prev." in os.path.basename(a):
            raise OSError(5, "Input/output error")
        return real(a, b)
    monkeypatch.setattr(os, "replace", replace)
    with pytest.raises(OSError) as e:
        host_results_tally(days=36499)
    assert e.value.errno == 28 and "the rollback failed" in str(e.value.__cause__)
    held = [p for p in ex.iterdir() if p.name.startswith(".RESULTS.md.") and ".prev." in p.name]
    assert len(held) == 1 and held[0].read_bytes() == old_md and held[0].name in str(e.value.__cause__)
    assert not (ex / "RESULTS.md").exists() and (ex / "results_tally.json").read_bytes() == old_js


def test_1006_codex_a_reused_pid_never_removes_an_earlier_runs_kept_markdown(tmp_path, monkeypatch):
    """Codex on #1006: the names carried the pid alone, so a later run under a reused pid removed an earlier run's kept
    previous Markdown (a failed rollback's only copy) as "a leftover" and again in its cleanup. Each run's names are its
    own now: an earlier run's file under this pid survives a whole run untouched."""
    import os

    from src.walters.export import host_results_tally
    ex = _world(tmp_path)
    host_results_tally(days=36500)
    kept = ex / f".RESULTS.md.{os.getpid()}.prev.tmp"                   # the old naming's kept copy, this pid
    kept.write_bytes(b"# an earlier run's previous Markdown")
    host_results_tally(days=36499)
    assert kept.read_bytes() == b"# an earlier run's previous Markdown"
    assert sorted(p.name for p in ex.iterdir() if p.name.startswith(".")) == [kept.name]


def test_1006_codex_a_new_markdown_that_cannot_be_removed_is_named_in_the_error(tmp_path, monkeypatch):
    """Codex on #1006: when the JSON's rename fails, the rollback fails and the new Markdown cannot be removed either,
    the mixed pair stands; the error says so (it was swallowed), naming the kept previous Markdown."""
    import os

    from src.walters.export import host_results_tally
    ex = _world(tmp_path)
    host_results_tally(days=36500)
    real_replace, real_unlink = os.replace, os.unlink

    def replace(a, b):
        if os.path.basename(b) == "results_tally.json":
            raise OSError(28, "No space left on device")
        if ".prev." in os.path.basename(a):
            raise OSError(5, "Input/output error")
        return real_replace(a, b)

    def unlink(p, *a, **k):
        if os.path.basename(p) == "RESULTS.md":
            raise OSError(30, "Read-only file system")
        return real_unlink(p, *a, **k)
    monkeypatch.setattr(os, "replace", replace)
    monkeypatch.setattr(os, "unlink", unlink)
    with pytest.raises(OSError) as e:
        host_results_tally(days=36499)
    why = str(e.value.__cause__)
    assert e.value.errno == 28 and "the previous RESULTS.md is kept as .RESULTS.md." in why
    assert "the new RESULTS.md could NOT be removed (OSError: Read-only file system): it stands beside" in why


def test_1006_codex_a_failed_rollback_on_a_first_export_names_no_kept_copy(tmp_path, monkeypatch):
    """Codex round 1 on #1006, found by its test: on a first export there is no previous Markdown, so the error never
    names a kept copy that does not exist."""
    import os

    from src.walters.export import host_results_tally
    ex = _world(tmp_path)
    real_replace, real_unlink = os.replace, os.unlink
    monkeypatch.setattr(os, "replace", lambda a, b: (_ for _ in ()).throw(OSError(28, "No space left on device"))
                        if os.path.basename(b) == "results_tally.json" else real_replace(a, b))

    def unlink(p, *a, **k):
        if os.path.basename(p) == "RESULTS.md":
            raise OSError(5, "Input/output error")
        return real_unlink(p, *a, **k)
    monkeypatch.setattr(os, "unlink", unlink)
    with pytest.raises(OSError) as e:
        host_results_tally(days=36499)
    why = str(e.value.__cause__)
    assert "there was no previous RESULTS.md" in why and "is kept as" not in why
    assert not [p for p in ex.iterdir() if ".prev." in p.name]
