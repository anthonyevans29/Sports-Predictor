"""THE RECORDS PR of addendum 298 item B.6, as ruled by addendum 299 item 3 (ARCHITECT 2026-11-08).

298 item B.6, verbatim in part: "RULED for a RECORDS PR (Code's records slot): registry entries for the two live models
quoting their certification rulings (the addenda and dates from BACKLOG), after which the line reads "certified" from
the registry. NFL's line as built."
299 item 3(a), verbatim in part: "the registry lookup is keyed by FAMILY and version, never by the bare version string
[...] `certification_of(family, model_version)` resolves them; a lookup without the family stays "unread"."
299 item 3(b), verbatim in part: "each entry quotes, verbatim and dated, the promotion record that put the model live
[...] If no such record exists for a model, the entry is NOT created, the line keeps reading "certification not read
(no registry entry)", and the records PR says so".

As built: soccer v22 has its entry (the BACKLOG entry of its 2026-09-21 re-promotion, quoted); MLB v2 has none (no
promotion record was found: its promotion predates both git history and BACKLOG's coverage). nfl-elo-v1 gains the one
key `family` and reads exactly as before. The tracked registry is read, never written."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))                 # the host modules' own import style

import closing as cl  # noqa: E402
import coverage_map as cm  # noqa: E402
import sp_common as c  # noqa: E402

from src.walters import exec_cohorts as xc  # noqa: E402
from src.walters import registry as reg  # noqa: E402

SOCCER = "soccer-elo-poisson-v22"
NFL = "nfl-elo-v1"
SHA = "b1746e93e841906493a6ac3b350cc5fe312161a6"
HEADING = "- **REBUILD COMPLETE + v22 RE-PROMOTED 2026-09-21 (the mountain,"
PREFIX = 'PROMOTED: 2026-09-21 — BACKLOG "'
# What main's registry read for NFL before this PR (origin/main 2336a77a): the closing page, results-tally and the
# bulletin all print from it.
NFL_BEFORE = ("uncertified", NFL)


def _entries():
    return reg.load()


def _by_id():
    return {e["id"]: e for e in _entries()}


def _backlog_entry(text: str) -> str:
    """The BACKLOG entry under HEADING, its list marker dropped and its line wraps folded to single spaces."""
    lines = text.split("\n")
    assert lines.count(HEADING) == 1                               # one entry opens so (a compiled fragment never does)
    i = lines.index(HEADING)
    block = []
    for ln in lines[i:]:
        if not ln.strip():
            break
        block.append(ln)
    assert block[0].startswith("- ") and all(x.startswith("  ") for x in block[1:])
    return " ".join([block[0][2:]] + [x[2:] for x in block[1:]])


def _main_registry(entries):
    """The registry as main held it: without the new entry and without nfl-elo-v1's `family`."""
    out = []
    for e in entries:
        if e["id"] == SOCCER:
            continue
        out.append({k: v for k, v in e.items() if not (e["id"] == NFL and k == "family")})
    return out


# ------------------------------------------------------------------------------------------------ the entries --

def test_the_soccer_entry_is_there_and_no_mlb_entry_was_created():
    by = _by_id()
    e = by[SOCCER]
    assert (e["family"], e["model_version"], e["model_family"], e["sport"]) == ("SOCCER", "v22", "soccer_elo_poisson",
                                                                                "soccer")
    assert e["status"] == "production" and e["run"] is None and e["verdict"] is None
    for k in ("declaration", "training_cutoff", "test_set", "gate", "confirmation_window", "declared_at"):
        assert e[k] is None, k                                     # law 4: not on record, never reconstructed
    assert "not on record" in e["declared_at_note"]
    # 299 item 3(b): MLB v2 has no promotion record, so no entry: no id, no MLB family, no entry naming its version
    assert "mlb-v2" not in by
    assert not any(x.get("family") == "MLB" for x in by.values())
    assert not any(x.get("model_version") == "v2" for x in by.values())
    # every entry that names a model carries its family (the lookup's key)
    assert {x["id"]: x["family"] for x in by.values() if x.get("model_version")} == {SOCCER: "SOCCER", NFL: "NFL"}


def test_the_certification_is_the_promotion_record_quoted_verbatim_and_dated():
    e = _by_id()[SOCCER]
    cert = e["certification"]
    assert cert.startswith(PREFIX) and cert.endswith('"') and not reg.uncertified(e)
    quote = cert[len(PREFIX):-1]
    assert quote == _backlog_entry((ROOT / "BACKLOG.md").read_text())      # not one character written by hand
    assert quote.startswith("**REBUILD COMPLETE + v22 RE-PROMOTED 2026-09-21") and "v22 PROMOTED on 16,546 matches" in quote
    assert e["record_commit"]["sha"] == SHA and SHA in e["certification_note"]
    assert e["record_commit"]["at"] == "2026-09-21 11:12:12 -0400"


def test_the_record_commit_is_quoted_as_git_holds_it():
    """The commit that wrote the BACKLOG entry: its message verbatim, and the entry in its BACKLOG.md. CI's checkout is
    shallow, so where git does not hold the commit this test says so and skips."""
    got = subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%B", SHA], capture_output=True, text=True)
    if got.returncode != 0:
        pytest.skip(f"commit {SHA[:8]} not in this checkout (shallow clone)")
    e = _by_id()[SOCCER]
    assert e["record_commit"]["message"] == got.stdout.strip()
    shown = subprocess.run(["git", "-C", str(ROOT), "show", f"{SHA}:BACKLOG.md"], capture_output=True, text=True)
    if shown.returncode != 0:                      # a partial / object-filtered clone: the commit without its tree
        pytest.skip(f"BACKLOG.md at {SHA[:8]} not in this checkout (partial clone)")
    assert _backlog_entry(shown.stdout) == e["certification"][len(PREFIX):-1]


def test_nfl_elo_v1_gains_only_its_family():
    e = _by_id()[NFL]
    assert e["family"] == "NFL"
    keys = list(e)
    assert keys.index("family") == keys.index("model_version") - 1
    assert e["certification"] == "UNCERTIFIED — shadow, confirmation window (addendum 214 item 3)"


def test_the_file_keeps_its_format_and_the_entry_sits_before_every_declaration():
    raw = (ROOT / "docs" / "registry" / "experiments.json").read_text()
    assert raw == json.dumps(json.loads(raw), indent=2) + "\n"
    ids = [e["id"] for e in _entries()]
    assert ids.count(SOCCER) == 1 and ids.index(SOCCER) == 0


# ------------------------------------------------------------------------------------ the family-keyed lookup --

def test_the_lookup_is_keyed_by_family_and_version():
    assert reg.certification_of("SOCCER", "v22") == ("certified", SOCCER)
    assert reg.certification_of("NFL", "nfl_elo_v1") == NFL_BEFORE
    # the bare version names no model: an MLB v22, a soccer nfl_elo_v1, an NFL v22 are not those entries
    assert reg.certification_of("MLB", "v22") == ("unread", "no registry entry for MLB v22")
    assert reg.certification_of("NFL", "v22") == ("unread", "no registry entry for NFL v22")
    assert reg.certification_of("SOCCER", "nfl_elo_v1") == ("unread", "no registry entry for SOCCER nfl_elo_v1")
    assert reg.certification_of("SOCCER", "v21") == ("unread", "no registry entry for SOCCER v21")
    assert reg.certification_of("soccer", "v22")[0] == "unread"              # the closing family string, exactly


def test_mlb_v2_keeps_reading_not_read():
    """299 item 3(b): no promotion record, no entry: "certification not read (no registry entry)"."""
    assert reg.certification_of("MLB", "v2") == ("unread", "no registry entry for MLB v2")


@pytest.mark.parametrize("family", [None, "", 0])
def test_a_lookup_without_the_family_stays_unread(family):
    assert reg.certification_of(family, "v22") == ("unread", reg.NO_FAMILY_WHY)
    assert reg.certification_of(family, "nfl_elo_v1") == ("unread", reg.NO_FAMILY_WHY)
    assert "no family given" in reg.NO_FAMILY_WHY


def test_the_path_is_keyword_only(tmp_path):
    """A path passed by position would land in the version (exec_cohorts passed it so before): refused by Python."""
    with pytest.raises(TypeError):
        reg.certification_of("NFL", "nfl_elo_v1", str(tmp_path / "x.json"))


def test_an_entry_without_a_family_is_never_read_certified(tmp_path):
    p = tmp_path / "r.json"
    p.write_text(json.dumps([{"id": "x", "model_version": "v22", "certification": "PROMOTED: fixture"}]))
    assert reg.certification_of("SOCCER", "v22", path=str(p)) == ("unread", "no registry entry for SOCCER v22")
    p.write_text(json.dumps([{"id": "x", "family": "MLB", "model_version": "v22", "certification": "UNCERTIFIED — f"}]))
    assert reg.certification_of("SOCCER", "v22", path=str(p))[0] == "unread"
    assert reg.certification_of("MLB", "v22", path=str(p)) == ("uncertified", "x")


# ------------------------------------------------------------------------------------- NFL and readers unchanged --

def test_nfl_certification_returns_exactly_what_it_returned_before():
    assert cl.nfl_certification() == NFL_BEFORE
    assert xc.nfl_certification() == NFL_BEFORE
    assert xc.nfl_certification(reg.LEDGER) == NFL_BEFORE


def test_uncertified_live_without_a_family_reads_as_on_main():
    """coverage_map.model_status calls uncertified_live(model, entries) with no family: on every version the tracked
    registry names (and none), the same entry, or None, as main's registry gives."""
    now, main = _entries(), _main_registry(_entries())
    for mv in ("v22", "v2", "nfl_elo_v1", "nfl_elo_v2", "", None):
        a, b = reg.uncertified_live(mv, now), reg.uncertified_live(mv, main)
        assert (a and a["id"]) == (b and b["id"]), mv
    assert reg.uncertified_live("nfl_elo_v1", now)["id"] == NFL
    assert reg.uncertified_live("nfl_elo_v1", now, family="NFL")["id"] == NFL
    assert reg.uncertified_live("nfl_elo_v1", now, family="SOCCER") is None
    assert reg.uncertified_live("nfl_elo_v1", now, family="")["id"] == NFL        # empty: the bare (conservative) match


def test_the_coverage_tile_reads_as_on_main(tmp_path, monkeypatch):
    """The coverage tile (cli.py coverage) on the tracked registry and on main's: every family's status, label, source
    and withholding id is the same."""
    monkeypatch.setattr(c, "HOST_ENV", tmp_path / "no-host.env")
    monkeypatch.setattr(c, "_DOTENV_CACHE", {})
    monkeypatch.delenv("SP_NHL_ACTIVE_FROM", raising=False)
    lanes, entries, unread = cm.read_ledgers()
    assert unread is None and SOCCER in entries
    main = {e["id"]: e for e in _main_registry(list(entries.values()))}
    prod = {("mlb", "mlb_pythag_negbin"): ["v2"], ("soccer", "soccer_elo_poisson"): ["v22"]}
    day = cl.ny_date(cl.clock())
    for code in ("PL", "MLB", "NFL", "NHL", "UNL", "NCAA", "PD", "CL"):
        got, was = (cm.model_status(code, lanes, x, prod, day=day) for x in (entries, main))
        assert got == was, code


def test_an_uncertified_entry_without_a_family_still_withholds_a_family_lookup(tmp_path):
    """Review of the records PR (law 4): an UNCERTIFIED entry naming the version whose `family` is not recorded
    (registry.declare writes none) withholds a family lookup; it never lets another entry of that family read certified."""
    import json as _json
    from src.walters import registry as _reg
    p = tmp_path / "experiments.json"
    p.write_text(_json.dumps([
        {"id": "nfl-elo-v1", "sport": "nfl", "status": "x", "family": "NFL", "model_version": "nfl_elo_v1",
         "certification": "PROMOTED x"},
        {"id": "nfl-hold", "sport": "nfl", "status": "x", "model_version": "nfl_elo_v1",
         "certification": "UNCERTIFIED - held"}]))
    assert _reg.certification_of("NFL", "nfl_elo_v1", path=str(p)) == ("uncertified", "nfl-hold")
