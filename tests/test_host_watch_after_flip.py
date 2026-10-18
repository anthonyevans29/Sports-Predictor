"""THE HOST'S CLOSING WATCH AFTER THE FLIP (ARCHITECT 2026-10-17 10:55 ET, addendum 113, FOR CODE), verbatim: "FOR
CODE (one PR, after addendum 112's items): the host closing-watch coverage after the flip — every family the laptop's
watch covers today (SOCCER, NFL; MLB stays laptop) is covered by the host's watch under role host with the fence lifted
by the flip; a test that the switch the cutover PR turns off is the same one the fence reads;
docs/specs/h2-cutover-runbook.md gains this plan's dates as "the 2026-10 schedule" without changing a step."
Addendum 114 item 3, verbatim: ""Lifted by the flip" (addendum 113) and "the named switch the cutover PR turns off"
(addendum 110) are the same thing: the cutover PR does the flip and turns the switch off in the same change; the fence
reads the switch, never SP_WRITER_OF_RECORD. Code's reading is the ruling."

THE FLIP AS THE CUTOVER PR MAKES IT, both halves in one change: sp_cutover.py's own `flip` step writes
SP_WRITER_OF_RECORD=host into host.env (step_flip, run here unchanged against a scratch host.env), and the switch the
fence reads, desk_policy.HOST_FENCE_RULE, is turned off (here monkeypatched, as the cutover PR's one source line will
set it). The host's watch is the unit's own command line (deploy/hosting/systemd/sp-closing-watch.service ExecStart),
run with host.env loaded into the environment as the unit's EnvironmentFile loads it; the laptop's watch today is
scripts/setup_closing_watch.sh with no --family (its default, MLB NFL SOCCER). The closing run's export step is
`python cli.py export-predictions --desk` in a child process; here the box's fake step annotates the export at the step
(desk_policy.annotate, reading the role and the switch as they are then).
The in-process identity test is #580's tests/test_desk_host_fence.py::
test_the_switch_the_cutover_pr_turns_off_is_the_one_the_fence_reads (the switch off lifts the fence under every role;
SP_WRITER_OF_RECORD anywhere, and sp_common.writer_of_record(), change nothing; desk_policy names neither). This file
adds what addendum 113 asks that it does not: the watch's families before and after the flip, the closed rows under
each half of the flip, and the ONE switch (one name, written nowhere but its own definition and desk_policy's two
restoring context managers, a line of code a fresh process reads whatever host.env and the environment say).
Every side effect is the box's (tests/test_closing_runs.py): a scratch schedule in a throwaway DB under tmp_path, no
real step, page, push or network."""
import ast
import contextlib
import gc
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

import pytest

from src.walters import desk_policy as dp
from tests.test_closing_runs import (  # noqa: F401  (box is a fixture)
    HOSTING, MACHINE, NOW, ROOT, at, box, c, call_pages, mc, nfl_doc, pl_doc, runs)
from tests.test_desk_host_fence import NOW as FENCE_NOW, REASON, intl_unl, mun_ful

import sp_cutover  # noqa: E402  (deploy/hosting is on sys.path: tests.test_closing_runs puts it there)

UNIT = HOSTING / "systemd" / "sp-closing-watch.service"
SETUP = ROOT / "scripts" / "setup_closing_watch.sh"
EXAMPLE = HOSTING / "etc" / "host.env.example"
RUNBOOK = ROOT / "docs" / "specs" / "h2-cutover-runbook.md"
HOST_KEYS = ("SP_WRITER_OF_RECORD", "SP_SKIP_FAMILIES", "SP_EXPORTS_MIRROR_ROLE")   # host.env.example's lines
SWITCH = "HOST_FENCE_RULE"
MLB_REFUSAL = "laptop only: SP_SKIP_FAMILIES names MLB here (the host cannot reach the MLB feed)"


# ------------------------------------------------------------------------------------------------ helpers --

def laptop_watch_today() -> tuple[str, ...]:
    """The laptop's watch today: scripts/setup_closing_watch.sh with no --family installs its default, the three."""
    sh = SETUP.read_text()
    m = re.search(r"if \[\[ \$\{#FAMILIES\[@\]\} -eq 0 \]\]; then FAMILIES=\(([A-Z ]+)\); fi", sh)
    assert m, "the setup script's default families line"
    return tuple(m.group(1).split())


def host_unit_argv() -> list[str]:
    """The host's watch: the unit's ExecStart after closing.py (P2: by name, never bare)."""
    lines = [x for x in UNIT.read_text().splitlines() if x.startswith("ExecStart=")]
    assert len(lines) == 1
    m = re.fullmatch(r"ExecStart=/opt/sports-predictor/venv/bin/python deploy/hosting/closing\.py (watch( --family "
                     r"[A-Z]+)+)", lines[0])
    assert m, lines[0]
    return m.group(1).split()


def families_of(argv) -> tuple[str, ...]:
    return tuple(argv[i + 1] for i, a in enumerate(argv) if a == "--family")


def host_env(box, monkeypatch) -> Path:
    """The host's host.env, its writer, families and role lines as deploy/hosting/etc/host.env.example ships them
    (writer laptop, SP_SKIP_FAMILIES=MLB, role host), read by the closing watch (sp_common.HOST_ENV) and by the Desk
    (SP_HOST_ENV, read first)."""
    ex = c.parse_env_file(EXAMPLE)
    assert {k: ex[k] for k in HOST_KEYS} == {"SP_WRITER_OF_RECORD": "laptop", "SP_SKIP_FAMILIES": "MLB",
                                             "SP_EXPORTS_MIRROR_ROLE": "host"}
    p = box.tmp / "etc" / "host.env"
    p.parent.mkdir(exist_ok=True)
    p.write_text("".join(f"{k}={ex[k]}\n" for k in HOST_KEYS))
    monkeypatch.setattr(c, "HOST_ENV", p)
    monkeypatch.setenv("SP_HOST_ENV", str(p))
    return p


def environment_file(p: Path, monkeypatch) -> None:
    """The unit's EnvironmentFile=-/etc/sports-predictor/host.env: every line of host.env in the process environment."""
    for k, v in c.parse_env_file(p).items():
        monkeypatch.setenv(k, v)


def flip_writer(p: Path, monkeypatch) -> dict:
    """The flip's first half, sp_cutover.py's own `flip` step, unchanged: SP_WRITER_OF_RECORD=host in host.env."""
    monkeypatch.setattr(sp_cutover, "_euid", lambda: 1000)               # in-process (CI may run as root)
    # step_flip writes os.environ["SP_WRITER_OF_RECORD"] itself (sp_cutover.py, after its write), outside monkeypatch.
    # A bare delenv of an absent variable records no undo, so that write would outlive the test; setenv first records
    # the prior state (absent or a value), and teardown puts it back.
    monkeypatch.setenv("SP_WRITER_OF_RECORD", "laptop")
    monkeypatch.delenv("SP_WRITER_OF_RECORD")
    ctx = sp_cutover.Ctx(pack=None, timers_file=p.parent / "timers.enabled",
                         runner=lambda argv: (1, "no systemctl in this test"), cutover_id="pack_20261026T1300")
    rec = sp_cutover.step_flip(ctx)
    assert (rec["exit"], rec["before"], rec["after"]) == (0, "laptop", "host")
    assert c.parse_env_file(p) == {"SP_WRITER_OF_RECORD": "host", "SP_SKIP_FAMILIES": "MLB",
                                   "SP_EXPORTS_MIRROR_ROLE": "host"}
    return rec


def switch_off(monkeypatch) -> None:
    """The flip's second half: the cutover PR's line, HOST_FENCE_RULE = {"on": False}."""
    monkeypatch.setitem(dp.HOST_FENCE_RULE, "on", False)


def desk_at_the_export_step(box, monkeypatch) -> None:
    """The export step's Desk runs at the step, under the role and the switch as they are then (the real step is a
    child process: `python cli.py export-predictions --desk` / `export-nfl-predictions --desk`)."""
    inner = box.fake_step

    def step(argv, run_id):
        if argv[0] == "export-predictions" and "--date" not in argv:
            box.docs["SOCCER"] = pl_doc()
        elif argv[0] == "export-nfl-predictions":
            box.docs["NFL"] = nfl_doc()
        return inner(argv, run_id)
    monkeypatch.setattr(mc, "run_step", step)


def the_hosts_tick(box, monkeypatch) -> int:
    """One tick of the host's unit at NOW: its own argv, through closing.py's main()."""
    desk_at_the_export_step(box, monkeypatch)
    monkeypatch.setattr(mc, "clock", lambda: NOW)
    return mc.main(host_unit_argv())


def closing_file(box, fam: str) -> dict:
    files = sorted((box.repo / "exports").glob(f"closing_{fam}_*.json"))
    assert len(files) == 1, files
    return json.loads(files[0].read_text())


def closed(box, fam: str) -> dict:
    """The closing file's rows (exports/closing_<FAMILY>_<start>.json: the games on the page, each row as the run's
    export gave it): match id -> its desk block (the receipt's desk_rows carry no pass_kind or reason)."""
    return {r["match_id"]: r["desk"] for r in closing_file(box, fam)["predictions"]}


def laptop_desks() -> dict:
    """The laptop's Desk calls for the same rows (conftest pins role laptop): family -> match id -> desk block."""
    assert dp.machine_role() == "laptop" and dp.HOST_FENCE_RULE["on"] is True
    return {"NFL": {r["match_id"]: r["desk"] for r in nfl_doc()["predictions"]},
            "SOCCER": {r["match_id"]: r["desk"] for r in pl_doc()["predictions"]}}


def covered(desks: dict, ids) -> dict:
    return {m: desks[m] for m in ids}


NFL_COVERED, SOCCER_COVERED = (301, 304, 302, 303), (401, 402)     # the box's covers at NOW: the start at T-35 and
#                                                                    the 10 minutes after it (test_c2)


def page_of(box, fam: str) -> list[str]:
    pages = [p for p in call_pages(box) if p["title"].startswith(f"{fam} closing")]
    assert len(pages) == 1, pages
    return pages[0]["body"].splitlines()


# ============================================================================== the families, before and after ==

def test_the_hosts_watch_covers_every_family_the_laptops_covers_today_but_mlb_and_the_runbook_says_the_same():
    """Addendum 113: "every family the laptop's watch covers today (SOCCER, NFL; MLB stays laptop) is covered by the
    host's watch". Read from the files that install each watch: the laptop's setup script installs MLB, NFL and
    SOCCER today; the host's unit names NFL and SOCCER; after the flip the laptop's watch is installed again for MLB
    only (runbook section 1 step 7, addendum 45 P5) and the host's unit is enabled with the same two families
    (section 1 step 5b). Between them, after the flip, every family is watched once: no family twice, none unwatched."""
    laptop_today = laptop_watch_today()
    host = families_of(host_unit_argv())
    assert laptop_today == ("MLB", "NFL", "SOCCER") == tuple(mc.FAMILIES)
    assert host == tuple(f for f in laptop_today if f != "MLB") == ("NFL", "SOCCER")
    rb = RUNBOOK.read_text()
    step_5b = rb[rb.index("5b. **TERMINAL (host): the host's closing watch"):
                 rb.index("6. **Fresh-fingerprint compare**")]
    step_7 = rb[rb.index("7. **TERMINAL (laptop)** (H2 step 7)"):rb.index("## 2. Fresh-fingerprint compare")]
    host_cmds = re.findall(r"closing\.py (?:preflight|test-page|watch)((?: --family [A-Z]+)+)", step_5b)
    assert len(host_cmds) == 4 and {families_of(x.split()) for x in host_cmds} == {host}   # preflight, test page,
    # dry run, and the unit's line
    assert f"closing.py watch {' '.join(host_unit_argv()[1:])}" in step_5b       # the unit's own line, by name
    laptop_after = re.findall(r"(?:setup_closing_watch\.sh|closing-watch)((?: --family [A-Z]+)+)", step_7)
    assert len(laptop_after) == 2 and {families_of(x.split()) for x in laptop_after} == {("MLB",)}
    assert set(host) | {"MLB"} == set(laptop_today) and not set(host) & {"MLB"}
    assert "--uninstall" in rb[rb.index("## 1. Cutover morning"):rb.index("2. **TERMINAL (host)** (H2 step 2)")]


def test_nothing_in_the_watch_reads_the_writer_of_record():
    """The flip's first half changes nothing in the watch itself: closing.py and chains.py never read
    SP_WRITER_OF_RECORD (the receipt line records it through sp_common.append_receipt, a record, not a decision), so
    the host's watch covers the unit's families whatever host.env's writer line says. The test below runs the tick
    under every combination."""
    for f in (HOSTING / "closing.py", HOSTING / "chains.py", UNIT):
        text = f.read_text()
        assert "WRITER_OF_RECORD" not in text.upper() and "writer_of_record" not in text, f.name


# ================================================================================== (a) after the flip ==

def test_a_after_the_flip_the_hosts_watch_closes_nfl_and_soccer_and_the_soccer_rows_are_not_fenced(box, monkeypatch):
    """(a) Under role host, with SP_WRITER_OF_RECORD=host (sp_cutover's own flip step) and HOST_FENCE_RULE off (the
    cutover PR's line), the host's tick runs NFL and SOCCER, each a success paged as `machine: host`; the soccer rows
    it closes are the model's calls, the laptop's Desk calls for the same rows, never host_fence (Arsenal's PLAY is on
    the page and in the closing file, whose desk_meta reads host_fence_rule false); NFL's are the laptop's too. MLB
    stays the laptop's: the unit does not name it and host.env's SP_SKIP_FAMILIES=MLB refuses a run typed by hand. The
    INTL rows the one switch fenced with soccer (addendum 115 item 3a) are lifted with them; INTL has no closing family
    (C1), so no watch closes them today."""
    lap = laptop_desks()
    p = host_env(box, monkeypatch)
    rec = flip_writer(p, monkeypatch)
    switch_off(monkeypatch)
    environment_file(p, monkeypatch)                   # resume starts the timers: the unit reads the new host.env
    assert c.writer_of_record() == "host" and mc.mirror_role() == "host" and dp.machine_role() == "host"
    assert rec["changed"] is True and Path(rec["kept_copy"]).read_text().startswith("SP_WRITER_OF_RECORD=laptop")
    assert the_hosts_tick(box, monkeypatch) == 0
    assert [(r["family"], r["exit"], r["trigger"], r["writer_of_record"]) for r in runs()] == [
        ("NFL", 0, "watch", "host"), ("SOCCER", 0, "watch", "host")]
    soccer = closed(box, "SOCCER")
    assert soccer == covered(lap["SOCCER"], SOCCER_COVERED)
    assert (soccer[401]["call"], soccer[401]["units"]) == ("PLAY", 0.5) and soccer[401]["order"]["text"]
    assert all(d["pass_kind"] != dp.HOST_FENCE_KIND and d["reason"] != REASON for d in soccer.values())
    assert closing_file(box, "SOCCER")["desk_meta"]["host_fence_rule"] is False
    lines = page_of(box, "SOCCER")
    assert lines[1] == "Arsenal Visitors @ Arsenal · PLAY Arsenal 0.5u · BUY YES KXEPLGAME-26OCT11-ARSH @ 0.45 × 5"
    assert lines[-2:] == ["PASS: 1 game", "machine: host"]
    assert closed(box, "NFL") == covered(lap["NFL"], NFL_COVERED)
    nfl = page_of(box, "NFL")
    assert nfl[1].startswith("Buffalo Visitors @ Buffalo · PLAY Buffalo 1u") and nfl[-1] == "machine: host"
    assert mc.run("MLB", start=at(30), now=NOW) == 2 and runs("MLB")[-1]["refused"] == MLB_REFUSAL
    intl, _ = intl_desk()
    assert intl["call"] == "PLAY" and intl["pass_kind"] != dp.HOST_FENCE_KIND
    assert not {"UNL", "INTL"} & {comp for v in mc.FAMILIES.values() for comp in v["comps"]}


def intl_desk():
    doc = {"sport": "intl", "predictions": [intl_unl()]}
    dp.annotate(doc, now=FENCE_NOW)
    return doc["predictions"][0]["desk"], doc


def test_a_the_hosts_soccer_page_after_the_flip_is_the_laptops_page_but_for_the_machine_line(box, monkeypatch):
    """The same schedule and the same export, closed by the laptop's watch today and by the host's after the flip:
    the page and the closing file's rows read the same, but for the machine line."""
    desk_at_the_export_step(box, monkeypatch)
    assert mc.watch(now=NOW, families=("SOCCER",)) == 0                 # the laptop today (conftest: role laptop)
    lap_page, lap_rows = page_of(box, "SOCCER"), closing_file(box, "SOCCER")["predictions"]
    assert lap_page[-1] == MACHINE
    for x in [*(box.repo / "exports").glob("closing_SOCCER_*.json"), *(box.repo / "logs").glob("*soccer*"),
              c.receipts_path()]:                                       # another machine: its own files and receipts
        x.unlink()
    box.pages.clear()
    p = host_env(box, monkeypatch)
    flip_writer(p, monkeypatch)
    switch_off(monkeypatch)
    environment_file(p, monkeypatch)
    assert the_hosts_tick(box, monkeypatch) == 0
    assert page_of(box, "SOCCER") == lap_page[:-1] + ["machine: host"]
    assert closing_file(box, "SOCCER")["predictions"] == lap_rows


# ================================================================================= (b) before the flip ==

def test_b_before_the_flip_the_hosts_soccer_rows_are_fenced_and_nfl_is_not(box, monkeypatch):
    """(b) Before the flip (role host, SP_WRITER_OF_RECORD=laptop, the fence on, as the host is today): the same
    tick closes NFL and SOCCER, and every soccer row it closes is PASS host_fence with the ruled reason, so the page
    carries no PLAY (only the PASS count), and the closing file's desk_meta reads host_fence_rule true. NFL's rows are
    the laptop's Desk calls, as after the flip."""
    lap = laptop_desks()
    p = host_env(box, monkeypatch)
    environment_file(p, monkeypatch)
    assert c.writer_of_record() == "laptop" and dp.HOST_FENCE_RULE["on"] is True and dp.machine_role() == "host"
    assert the_hosts_tick(box, monkeypatch) == 0
    assert [(r["family"], r["exit"], r["writer_of_record"]) for r in runs()] == [("NFL", 0, "laptop"),
                                                                                 ("SOCCER", 0, "laptop")]
    soccer = closed(box, "SOCCER")
    assert [(m, d["call"], d["units"], d["pass_kind"], d["reason"], d["order"]) for m, d in soccer.items()] == [
        (401, "PASS", 0, dp.HOST_FENCE_KIND, REASON, None), (402, "PASS", 0, dp.HOST_FENCE_KIND, REASON, None)]
    assert lap["SOCCER"][401]["call"] == "PLAY"                         # the call the fence holds back
    assert page_of(box, "SOCCER")[1:] == ["PASS: 2 games", "machine: host"]
    assert closing_file(box, "SOCCER")["desk_meta"]["host_fence_rule"] is True
    assert closed(box, "NFL") == covered(lap["NFL"], NFL_COVERED)
    assert page_of(box, "NFL")[1].startswith("Buffalo Visitors @ Buffalo · PLAY Buffalo 1u")


@pytest.mark.parametrize("writer_flipped", [False, True], ids=["writer laptop", "writer host"])
@pytest.mark.parametrize("switch_on", [True, False], ids=["switch on", "switch off"])
def test_the_switch_decides_the_soccer_rows_and_the_writer_line_decides_nothing(box, monkeypatch, writer_flipped,
                                                                                switch_on):
    """Addendum 114 item 3: "the fence reads the switch, never SP_WRITER_OF_RECORD." Each half of the flip alone, and
    both, and neither: the host's tick closes NFL and SOCCER in all four; the soccer rows are host_fence exactly when
    the switch is on (the flip without the switch is still fenced; the switch without the flip is lifted, the
    laptop's calls); NFL's rows are the laptop's in all four."""
    lap = laptop_desks()
    p = host_env(box, monkeypatch)
    if writer_flipped:
        flip_writer(p, monkeypatch)
    if not switch_on:
        switch_off(monkeypatch)
    environment_file(p, monkeypatch)
    assert c.writer_of_record() == ("host" if writer_flipped else "laptop")
    assert the_hosts_tick(box, monkeypatch) == 0
    assert [r["family"] for r in runs()] == ["NFL", "SOCCER"] and all(r["exit"] == 0 for r in runs())
    soccer = closed(box, "SOCCER")
    if switch_on:
        assert {m: (d["pass_kind"], d["reason"]) for m, d in soccer.items()} == {
            m: (dp.HOST_FENCE_KIND, REASON) for m in SOCCER_COVERED}
    else:
        assert soccer == covered(lap["SOCCER"], SOCCER_COVERED)
    assert closing_file(box, "SOCCER")["desk_meta"]["host_fence_rule"] is switch_on
    assert closed(box, "NFL") == covered(lap["NFL"], NFL_COVERED)


# ================================================================================== (c) the ONE switch ==

def _switches(tree: ast.Module) -> dict[str, int]:
    """desk_policy's policy switches: module-level NAME = {"on": <bool>} (name -> line)."""
    out = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Dict) and [getattr(k, "value", None) for k in node.value.keys] == ["on"]
                and isinstance(node.value.values[0], ast.Constant) and isinstance(node.value.values[0].value, bool)):
            out[node.targets[0].id] = node.lineno
    return out


def _functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def _names(fn: ast.FunctionDef) -> set[str]:
    return {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}


REFS = ("base_v11", "host_fence_rule_off", SWITCH)  # the switch, and desk_policy's two context managers that turn it off
REFS_IN_A_STRING = re.compile(rf"\b({'|'.join(REFS)})\b")
DESK_POLICY = "src/walters/desk_policy.py"
SKIP_PARTS = {"tests", ".claude", ".git", "venv", ".venv", "node_modules"}


def _tracked(*pathspec: str) -> list[str]:
    """The tracked files (git ls-files): untracked files, and the worktrees under the main checkout's .claude/,
    never count."""
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--", *pathspec], capture_output=True, text=True,
                         check=True).stdout.split("\0")
    return [f for f in out if f and (ROOT / f).is_file()]


def _production() -> list[Path]:
    return [ROOT / f for f in _tracked("*.py") if not (SKIP_PARTS & set(Path(f).parts))]


def _ident(node) -> str | None:
    return node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None


class _Record(NamedTuple):
    refs: set[tuple[str, str]]       # (function, how) for every reference to one of REFS (see _record)
    stores: list[tuple[str, int]]    # where the switch is written: (function, line)
    imports: set[str]                # every dotted part of every import, and every name a `from` import takes
    strings: list[str]               # the string constants the code uses; a bare string statement (a docstring) is not


def _record(tree: ast.AST) -> _Record:
    """One pass over a file's tree (each node once, with its enclosing function: "<module>" outside any def).
    refs: every ast.Name (its id) or ast.Attribute (its attr) that is one of REFS, so an alias (off =
    dp.host_fence_rule_off) and a write through one (rule = dp.HOST_FENCE_RULE) count where they are taken; how is
    the name, NAME["on"] when it is subscripted ["on"], or "NAME =" when it is assigned to; also "import NAME" for an
    import that takes one (a dotted part, an imported name or an `as` name), and 'NAME' for one in a string the code
    uses. stores: where the switch is written (NAME = ..., NAME[...] = ..., x.NAME = ..., x.NAME[...] = ...; a tuple
    target's elements too). imports: every dotted part of `import a.b` and of `from a.b import c` (relative ones
    too), and every name a `from` import takes (`from scripts import x`, `from . import x`)."""
    refs, stores, imports, strings = set(), [], set(), []
    bare, on = set(), set()                  # ids: the value of a bare expression statement; a value subscripted ["on"]
    stack = [(tree, "<module>")]
    pop, push = stack.pop, stack.append
    while stack:
        n, where = pop()                     # a parent always before its children
        kind = type(n)
        if kind is ast.Name or kind is ast.Attribute:
            name = n.id if kind is ast.Name else n.attr
            if name in REFS:
                how = f'{name}["on"]' if id(n) in on else f"{name} =" if type(n.ctx) is ast.Store else name
                refs.add((where, how))
            if kind is ast.Name:
                continue                     # no child but its ctx
        elif kind is ast.Constant:
            if type(n.value) is str and id(n) not in bare:
                strings.append(n.value)
                refs |= {(where, repr(x)) for x in REFS_IN_A_STRING.findall(n.value)}
            continue                         # no child
        elif kind is ast.Expr:
            bare.add(id(n.value))
        elif kind is ast.Subscript:
            if type(n.slice) is ast.Constant and n.slice.value == "on":
                on.add(id(n.value))
        elif kind is ast.Import or kind is ast.ImportFrom:
            taken = n.module.split(".") if kind is ast.ImportFrom and n.module else []
            for a in n.names:
                taken += [*(a.name.split(".") if kind is ast.Import else [a.name]), a.asname]
            imports.update(x for x in taken if x)
            refs |= {(where, f"import {x}") for x in taken if x in REFS}
            continue                         # its children are aliases, read above
        elif kind is ast.Assign or kind is ast.AugAssign or kind is ast.AnnAssign:
            for t in (n.targets if kind is ast.Assign else [n.target]):
                for e in (t.elts if type(t) is ast.Tuple else [t]):
                    if _ident(e.value if type(e) is ast.Subscript else e) == SWITCH:
                        stores.append((where, n.lineno))
        elif kind is ast.FunctionDef or kind is ast.AsyncFunctionDef:
            where = n.name                   # its children are in it
        for field in n._fields:              # ast.iter_child_nodes, inline
            v = getattr(n, field, None)
            if type(v) is list:
                for x in v:
                    if isinstance(x, ast.AST):
                        push((x, where))
            elif isinstance(v, ast.AST):
                push((v, where))
    return _Record(refs, stores, imports, strings)


@contextlib.contextmanager
def _collector_paused():
    """The tracked files parse to ~600k AST nodes, each tree freed by its refcount once its record is taken (no
    cycles). With the collector on, its passes over a whole session's heap cost more than the parsing (test (c) took
    2.36s in the full suite, 1.4s alone); paused, 1.19s in the suite and about 1.1s alone. Put back as it was."""
    was = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if was:
            gc.enable()


def _words(stems: set[str]) -> re.Pattern:
    """Any of `stems` as a whole word (\\bstem\\b), the longest tried first; no stems matches nothing."""
    if not stems:
        return re.compile(r"(?!)")
    return re.compile(rf"\b(?:{'|'.join(map(re.escape, sorted(stems, key=len, reverse=True)))})\b")


def _named_in_code(rec: _Record, stems: set[str], words: re.Pattern) -> set[str]:
    """Which of `stems` (words: _words(stems)) the file imports or names in a string its code uses (a path it runs);
    not a docstring."""
    return (rec.imports & stems) | set(words.findall("\0".join(rec.strings)))


def test_c_one_switch_the_cutover_pr_turns_off_and_nothing_else_lifts_the_fence():
    """(c) What #580's identity test (test_desk_host_fence.py::test_the_switch_the_cutover_pr_turns_off_is_the_one_
    the_fence_reads) does not pin: there is ONE switch for the cutover PR to turn off. Of desk_policy's policy switches
    (NAME = {"on": bool}) exactly one is the fence's, HOST_FENCE_RULE, and it is the only one the fence's read path
    (host_fenced, role_reading, machine_role, _env_file) names; that path names no other setting than the role and the
    two env files, and no WRITER string. The fence is checked in one place, first in _desk_call. In the tracked
    production code HOST_FENCE_RULE is assigned nowhere but its own definition and desk_policy's two context managers
    that turn it off and put it back (base_v11 for the frozen golden, host_fence_rule_off for comparisons). Every
    reference counts (_record: a name or an attribute, so an alias or a write through one too; an import; a string the
    code uses). In desk_policy the switch is referenced only as its definition and as HOST_FENCE_RULE["on"] (in
    host_fenced, annotate's desk_meta and the two context managers): no alias, no method call, never handed on; and
    neither context manager is referenced in its code. No other tracked production file references the switch, and
    only four verify/battery scripts reference a context manager (scripts/cockpit_btrack_verify.py,
    cockpit_desk_files.py, cockpit_window_verify.py, desk_battery.py; each dp.base_v11). Neither they nor any script
    importing them (any dotted part of an import, or a name a `from` import takes) is imported or named in a string
    the code uses (a path it runs) by cli.py, src/, deploy/ (chains.py, closing.py and the units included) or the
    laptop's setup scripts, and the four are not named there at all, but one: cutover-readiness
    (deploy/hosting/cutover_readiness.py) runs the parity harness, scripts/desk_parity_verify.py (desk_battery's
    base_v11), as a child process in a scratch worktree of a release tag with a scratch DB, criterion (c); it does not
    import it. So in production the switch is off only by the source line, the cutover PR's line: outside desk_policy,
    no file on an export, chain, closing or deploy path references the switch or either context manager, or imports
    a script that does. The desk_meta key the runbook's after-flip check reads (host_fence_rule) is that switch."""
    src = Path(dp.__file__).read_text()
    tree = ast.parse(src)
    switches = _switches(tree)
    assert [s for s in switches if "FENCE" in s] == [SWITCH] and dp.HOST_FENCE_RULE == {"on": True}
    fns = _functions(tree)
    path = ("host_fenced", "role_reading", "machine_role", "_env_file")
    assert {s for f in path for s in _names(fns[f]) & set(switches)} == {SWITCH}
    assert _names(fns["host_fenced"]) & set(switches) == {SWITCH}
    strings = [n.value for f in path for n in ast.walk(fns[f]) if isinstance(n, ast.Constant)
               and isinstance(n.value, str)]
    assert not [s for s in strings if "WRITER" in s.upper()]
    assert {s for s in strings if re.fullmatch(r"[A-Z][A-Z0-9_]+", s)} == {"SP_HOST_ENV"}      # host.env's path
    assert {"ROLE_ENV", "HOST_ENV_DEFAULT", "DOTENV"} <= _names(fns["role_reading"])          # the role, the files
    assert dp.ROLE_ENV == "SP_EXPORTS_MIRROR_ROLE"
    calls =[f for f, fn in fns.items() if any(isinstance(n, ast.Call) and getattr(n.func, "id", None) == "host_fenced"
                                                for n in ast.walk(fn))]
    assert calls == ["_desk_call"]
    first = fns["_desk_call"].body[1]                                   # after the docstring: the fence, first
    assert isinstance(first, ast.Assign) and getattr(first.value.func, "id", None) == "host_fenced"
    own = _record(tree)
    assert sorted({w for w, _ in own.stores}) == ["<module>", "base_v11", "host_fence_rule_off"]
    assert [ln for w, ln in own.stores if w == "<module>"] == [switches[SWITCH]]
    assert re.search(r'"host_fence_rule": HOST_FENCE_RULE\["on"\]', src)
    assert sorted(own.refs) == [("<module>", f"{SWITCH} ="), ("annotate", f'{SWITCH}["on"]'),     # desk_meta's key
                                ("base_v11", f'{SWITCH}["on"]'), ("host_fence_rule_off", f'{SWITCH}["on"]'),
                                ("host_fenced", f'{SWITCH}["on"]')]
    assert Path(dp.__file__).resolve() == ROOT / DESK_POLICY
    production = _production()
    assert len(production) > 50 and ROOT / DESK_POLICY in production
    texts, records = {}, {}
    with _collector_paused():
        for p in production:                                            # each file parsed once, its tree walked once
            f = str(p.relative_to(ROOT))
            texts[f] = p.read_text(encoding="utf-8", errors="replace")
            records[f] = own if f == DESK_POLICY else _record(ast.parse(texts[f]))
    writers = {f: sorted({w for w, _ in r.stores}) for f, r in records.items() if r.stores}
    assert writers == {DESK_POLICY: ["<module>", "base_v11", "host_fence_rule_off"]}
    refs = {f: sorted({how for _, how in r.refs}) for f, r in records.items() if r.refs and f != DESK_POLICY}
    assert refs == {f"scripts/{s}.py": ["base_v11"] for s in (
        "cockpit_btrack_verify", "cockpit_desk_files", "cockpit_window_verify", "desk_battery")}
    # who references them, and every script that imports one of those (to the end of the chain)
    helpers = {Path(f).stem for f in refs}
    scripts = {Path(f).stem: r.imports for f, r in records.items() if Path(f).parent == Path("scripts")}
    reach = set(helpers)
    while more := {s for s, imports in scripts.items() if s not in reach and imports & reach}:
        reach |= more
    assert {"desk_parity_verify", "desk_golden_capture", "cockpit_render_verify"} <= reach
    # the export, chain, closing and deploy paths: cli.py, src/, deploy/ (python, units, shell, env files), and the
    # laptop's setup scripts (its launchd jobs)
    paths = [f for f in _tracked("cli.py", "src", "deploy", "scripts/setup_*.sh") if not f.endswith(".md")]
    assert "deploy/hosting/chains.py" in paths and "deploy/hosting/closing.py" in paths and len(paths) > 150
    four, reached = _words(helpers), _words(reach)
    direct, named = {}, {}
    for f in paths:
        text = texts[f] if f in texts else (ROOT / f).read_text(encoding="utf-8", errors="replace")
        if hit := set(four.findall(text)):                              # the four, even in a docstring
            direct[f] = sorted(hit)
        hit = _named_in_code(records[f], reach, reached) if f in records else set(reached.findall(text))
        if hit:
            named[f] = sorted(hit)
    assert direct == {}
    assert named == {"deploy/hosting/cutover_readiness.py": ["desk_parity_verify"]}     # parity_on(): a child process
    assert "desk_parity_verify" not in records["deploy/hosting/cutover_readiness.py"].imports  # on a scratch worktree


def test_c_a_fresh_process_on_the_flipped_host_reads_the_switch_from_the_source_and_is_still_fenced(box, monkeypatch):
    """The closing run's export step is a child process (`python cli.py export-predictions --desk`): what it reads is
    the source line, not this process's state. On the host after sp_cutover's own flip (host.env: writer host, role
    host; SP_WRITER_OF_RECORD=host in the environment, as the unit loads it), a fresh process runs the runbook's own
    HOST FENCE CHECK command (section 0, before step 4's flip) and prints {'on': True} today, and a soccer row there is
    PASS host_fence with desk_meta.host_fence_rule true: the flip alone does not lift the fence. In production only the
    cutover PR's line does (what test (c) pins; the runbook's check then prints {'on': False})."""
    p = host_env(box, monkeypatch)
    flip_writer(p, monkeypatch)
    environment_file(p, monkeypatch)
    rb = RUNBOOK.read_text()
    m = re.search(r'`sudo -u sp venv/bin/python -c "(from src\.walters\.desk_policy import (\w+); print\(\2\))"` '
                  r"prints `\{'on': False\}`", rb)
    assert m and m.group(2) == SWITCH                                   # the runbook's check reads the fence's switch
    env = dict(os.environ)
    assert env["SP_WRITER_OF_RECORD"] == "host" and env["SP_EXPORTS_MIRROR_ROLE"] == "host"
    out = subprocess.run([sys.executable, "-c", m.group(1)], cwd=ROOT, env=env, capture_output=True, text=True,
                         check=True)
    assert out.stdout.strip() == "{'on': True}"
    code = ("import json, sys; from datetime import datetime; from src.walters import desk_policy as dp; "
            "doc = json.load(sys.stdin); dp.annotate(doc, now=datetime.fromisoformat(sys.argv[1])); "
            "d = doc['predictions'][0]['desk']; "
            "print(json.dumps([dp.machine_role(), doc['desk_meta']['host_fence_rule'], d['call'], d['pass_kind'], "
            "d['reason']]))")
    doc = {"sport": "soccer", "predictions": [mun_ful()]}
    out = subprocess.run([sys.executable, "-c", code, FENCE_NOW.isoformat()], cwd=ROOT, env=env,
                         input=json.dumps(doc), capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == ["host", True, "PASS", dp.HOST_FENCE_KIND, REASON]


# ============================================================================== the runbook's 2026-10 schedule ==

def test_the_runbook_carries_the_2026_10_schedule_with_addendum_113s_dates():
    """Addendum 113: "docs/specs/h2-cutover-runbook.md gains this plan's dates as "the 2026-10 schedule" without
    changing a step." The section quotes the plan's six dated items verbatim, before section 0's steps."""
    rb = RUNBOOK.read_text()
    head = "## The 2026-10 schedule"
    assert rb.count(head) == 1 and rb.index(head) < rb.index("## 0. Before the ruling day")
    sec = rb[rb.index(head):rb.index("## 0. Before the ruling day")]
    quoted = " ".join(" ".join(x[2:] for x in sec.splitlines() if x.startswith("> ")).split())
    for quote in (
            "1. Sun 10-18 → Thu 10-22: the five morning compares.",
            "2. Sun 10-18 (laptop, any mode, no host): the dry run — `sp_cutover.py run --dry-run --scratch <DIR>` "
            "on a scratch pack (runbook section 0).",
            "3. Mon 10-19 evening (host, Tailscale): the P8 rehearsal — one host `closing-run --family NFL --start "
            "<the MNF start the laptop's watch paged>`;",
            "4. By Wed 10-21: v1.5.0.",
            "The host runs Thursday 10-22 on it: that is criterion (b)'s full day with desk calls; the parity harness "
            "runs on that tag Thursday: criterion (c).",
            "5. Thu 10-22 evening: `cli.py cutover-readiness` on the laptop; its GO / NOT-YET lines pasted to me. Fri "
            "10-23 morning: my ruling — cutover Monday 10-26, or named reasons and the 10-30 fallback.",
            "6. Mon 10-26 morning, 09:00–11:00 ET (no soccer that day; NFL only in the evening; the host's 13:05Z "
            "window tick is the first one to run on the new database):"):
        assert quote in quoted, quote
    for when in ("| Sun 10-18 → Thu 10-22 |", "| Sun 10-18 |", "| Mon 10-19 evening |", "| by Wed 10-21 |",
                 "| Thu 10-22 |", "| Thu 10-22 evening |", "| Fri 10-23 morning |",
                 "| Mon 10-26, 09:00–11:00 ET (fallback 10-30) |"):
        assert sec.count(when) == 1, when
