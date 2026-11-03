"""#816, ADDENDUM 239 (ARCHITECT 2026-11-03 16:15 ET). Pins, on the shadow's synthetic world, synthetic payloads and
scratch git repositories only (no real DB, no network, no host):
item 2, ORIENTATION COUNTS: a fixture whose CURRENT CFBD pregame row is 'swapped' (CFBD's home is our listed away) is
    priced exactly as the gate's walk prices it (ncaa_backtest.game_from_rows flips a swapped label: the 55 to CFBD's
    home), its probabilities stated for OUR listed home and away; 'same' prices our order; no current row (none, or a
    row from an older ingest, item 5): the listed home keeps the 55 and the row says "unknown"; parity() pins it;
item 3, THE FENCES: both lift together, on the run AND its verdict;
item 4, THE LEGS BOUNDARY: the repo record names no deploy instant for the tag carrying #475 (release Issue #556
    names none either), so 2026-10-14T04:00:00Z (the next ET midnight), the console saying why; one second before is never read, the instant is;
item 1(a), THE MIGRATION TAG: the deploy finds top-level migrate_*.py files by git (no list to register in); a release
    adding migrate_ncaa_cfbd_pregame.py in one ordinary commit names exactly it on the dry run."""
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.db.database import session_scope
from src.db.schema import Match, NCAACFBDPregame, OddsSnapshot
from src.walters import ncaa_backtest as nb
from src.walters import ncaa_shadow as sh
from src.walters import registry as reg
from tests.test_ncaa_shadow import NOW, mine, world  # noqa: F401  (fixtures: the shadow's synthetic world)
from tests.test_ncaa_v2_236_rulings import _grade, _kalshi, _pregame, _registry, clean, finished_up  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "deploy" / "hosting"))
SWAPPED_TEXT = "orientation: CFBD's home is our listed away (swapped); priced as the gate's walk"


def _walked():
    """The gate's model (NeutralRuleElo at the frozen s) walked over the stream before NOW, as the export walks."""
    m = nb.NeutralRuleElo(False, scale=sh.V2_FROZEN_S)
    sh.walk(m, nb.load_v1r_stream().games, NOW)
    return m


def _walk_game(mid, orientation, neutral):
    """The gate's walk's own Game for the stored fixture (ncaa_backtest.game_from_rows) under a CFBD row of this
    orientation and flag (no score yet)."""
    with session_scope() as s:
        m = s.get(Match, mid)
        lab = SimpleNamespace(orientation=orientation, home_score=None, away_score=None, neutral=neutral,
                              source_game_id=mid, season="2026", fetched_at=NOW)
        g = nb.game_from_rows(m, lab)
        s.rollback()
    return g


def _row(tmp_path, name):
    _, doc = sh.export(now=NOW, out_dir=str(tmp_path / name), registry_path=_registry(tmp_path), eid=sh.V2_EID)
    (r,) = doc["predictions"]
    return r["prediction"], doc


@pytest.mark.parametrize("neutral", [False, None, True])
def test_item_2_a_swapped_fixtures_shadow_probability_equals_the_walks(clean, tmp_path, neutral):
    t = clean["teams"]
    _pregame(clean["up"], neutral, orientation="swapped")
    p, doc = _row(tmp_path, f"s{neutral}")
    m = _walked()
    gw = _walk_game(clean["up"], "swapped", neutral)
    assert (gw.home_id, gw.away_id) == (t[1], t[0])                     # the walk's Game: CFBD's home first
    walk_p = m.predict(gw)                                              # P(CFBD's home wins), the gate's p
    assert p["away_win_prob"] == round(walk_p, 4)                       # our listed away = CFBD's home
    assert p["home_win_prob"] == round(1 - walk_p, 4)                   # stated for OUR listed home, never inverted
    assert p["top_pick"] == ("home_win" if 1 - walk_p >= 0.5 else "away_win")
    assert p["home_adv_applied"] == m.home_adv(gw) == (0.0 if neutral is True else 55.0)
    assert p["home_adv_to"] == (None if neutral is True else "listed_away")
    assert (p["orientation"], p["orientation_rule"]) == ("swapped", SWAPPED_TEXT)
    assert (p["elo_home"], p["elo_away"]) == (round(m.rating(t[0]), 1), round(m.rating(t[1]), 1))
    if neutral is not True:
        assert p["home_adv_basis"].startswith("CFBD's home (our listed away): ")
    assert doc["fit"]["orientation_pregame"] == {"swapped": 1}


def test_item_2_the_swap_moves_the_price_unless_neutral(clean, tmp_path):
    prices = {}
    for o in ("same", "swapped"):
        for flag in (False, True):
            _pregame(clean["up"], flag, orientation=o)
            prices[o, flag] = _row(tmp_path, f"{o}{flag}")[0]["home_win_prob"]
    assert prices["same", False] != prices["swapped", False]            # the 55 changes sides
    assert prices["same", True] == prices["swapped", True]              # home advantage 0: symmetric


def test_item_2_same_prices_our_order_as_the_walk_does(clean, tmp_path):
    _pregame(clean["up"], False, orientation="same")
    p, doc = _row(tmp_path, "same")
    gw = _walk_game(clean["up"], "same", False)
    assert p["home_win_prob"] == round(_walked().predict(gw), 4)
    assert (p["orientation"], p["home_adv_to"]) == ("same", "listed_home")
    assert p["orientation_rule"] == "orientation: CFBD's home is our listed home (same); priced as the gate's walk"
    assert doc["fit"]["orientation_pregame"] == {"same": 1}


@pytest.mark.parametrize("state", ["none", "stale"])
def test_item_2_and_5_no_current_row_the_listed_home_keeps_it_unknown(clean, tmp_path, state):
    t = clean["teams"]
    with session_scope() as s:
        s.query(NCAACFBDPregame).filter(NCAACFBDPregame.match_id == clean["up"]).delete()
    if state == "stale":                                                # item 5: an older ingest's row is unknown
        _pregame(clean["up"], False, at=NOW - timedelta(days=3), orientation="swapped")
    p, doc = _row(tmp_path, state)
    m = _walked()
    listed = m.predict(nb.Game(t[0], t[1], "2026", NOW + timedelta(hours=5), 0, 0, "Regular Season"))
    assert p["home_win_prob"] == round(listed, 4)
    assert (p["orientation"], p["home_adv_applied"], p["home_adv_to"]) == ("unknown", 55.0, "listed_home")
    assert p["orientation_rule"].startswith("orientation: unknown")
    assert p["pregame_orientation"] is None                             # the stale row is never read
    assert doc["fit"]["orientation_pregame"] == {"unknown": 1}


def test_item_2_parity_pins_the_orientation_equal_to_the_gate():
    r = sh.parity(sh.synthetic_stream())
    assert r["swapped_compared"] == r["compared"] > 0
    assert r["swapped_unequal"] == 0 and r["swapped_max_diff"] <= sh.PARITY_TOL
    assert r["unoriented_max_diff"] > sh.PARITY_TOL                     # our listed order alone would not be parity
    line = sh.parity_lines(r)[2]
    assert line.startswith("  orientation (ARCHITECT 2026-11-03, addendum 239 item 2)") and "EQUAL" in line


def test_item_2_the_ruling_text_and_no_open_question_remain():
    assert sh.ORIENTATION_TEXT["swapped"] == SWAPPED_TEXT
    for f in ("docs/specs/ncaa-shadow.md", "src/walters/ncaa_shadow.py"):
        text = (ROOT / f).read_text()
        assert "whether 3(1)'s parity covers the orientation" not in text.lower()
        assert "orientation is open for the architect" not in text


# ------------------------------------------------------------------------------------------------ item 3 --

def test_item_3_both_fences_lift_together_on_the_run_and_its_verdict(finished_up, tmp_path, monkeypatch):
    from tests.test_ncaa_v2_236_rulings import RUN

    for name, verdict, run in (("norun.json", "PASS", None), ("noverdict.json", None, RUN)):
        monkeypatch.setattr(reg, "LEDGER", _registry(tmp_path, name=name, verdict=verdict, run=run))
        assert sh.kalshi_fenced() is True
    monkeypatch.setattr(reg, "LEDGER", finished_up["reg"])
    up = finished_up["up"]
    with session_scope() as s:
        m = s.get(Match, up)
        k = sh.KalshiClose(s, [m])
        assert k.fence is False
        for season in ("2023", "2026"):                                 # neither fence holds after the lift
            k.labs = {up: (season,)}
            assert k.pre(m) is None
        s.rollback()


# ------------------------------------------------------------------------------------------------ item 4 --

def test_item_4_the_record_names_no_deploy_instant_for_the_tag_carrying_475():
    """The fallback holds only while the record is silent: v1.4.0 (the first tag carrying #475) has a release line
    and no Deploy line in docs/RELEASES.md. A Deploy line added there must move KALSHI_LEGS_FROM with it."""
    text = (ROOT / "docs" / "RELEASES.md").read_text()
    assert "| `v1.4.0` | 2026-10-16 14:18:21Z |" in text
    sec = text[text.index("- **v1.4.0**"):text.index("- **v1.5.0**")]
    assert "**Deploy:**" not in sec
    assert sh.KALSHI_LEGS_FROM == datetime(2026, 10, 14, 4, 0, 0)       # 2026-10-14T04:00:00Z, naive UTC
    assert sh.LEGS_BEFORE == "legs_before_2026_10_14"


def test_item_4_one_second_before_the_boundary_is_never_read_the_instant_is(finished_up):
    up = finished_up["up"]
    with session_scope() as s:
        s.query(OddsSnapshot).filter(OddsSnapshot.match_id == up, OddsSnapshot.source == "kalshi").delete()
        _kalshi(s, up, 0.50, 0.52, datetime(2026, 10, 13, 4, 0))         # the old 00:00 ET floor: now before
        _kalshi(s, up, 0.55, 0.57, datetime(2026, 10, 14, 3, 59, 59))    # one second before the instant
    r = _grade(finished_up)
    assert r["kalshi_close_excluded"]["legs_before_2026_10_14"] == 1
    assert r["vs_kalshi_close"]["ncaa_elo_v2"]["games"] == 0
    assert ("the repo record (docs/RELEASES.md, BACKLOG.md, CHANGELOG.md, docs/, deploy/) names no deploy instant "
            "for the tag carrying #475, nor does v1.4.0's release Issue #556 (read: its Host section says \"Not deployed yet\" and no later comment records the deploy); the conservative bound is "
            "the next ET midnight, addendum 239 item 4") in r["kalshi_close_rule"]
    assert "legs placed before 2026-10-14T04:00:00Z (2026-10-14 00:00 ET)" in r["kalshi_close_rule"]
    with session_scope() as s:
        _kalshi(s, up, 0.60, 0.62, datetime(2026, 10, 14, 4, 0, 0))      # at the instant: read
    r = _grade(finished_up)
    assert r["kalshi_close_excluded"]["legs_before_2026_10_14"] == 0
    assert r["vs_kalshi_close"]["ncaa_elo_v2"]["games"] == 1 and "kalshi_close_H=0.610" in r["lines"][0]


# --------------------------------------------------------------------------------------------- item 1(a) --

def test_item_1a_the_deploy_finds_the_pregame_migration_without_a_list():
    import sp_deploy

    assert (ROOT / "migrate_ncaa_cfbd_pregame.py").is_file()           # top level, where _root_migrations looks
    assert sp_deploy.MIGRATION_NAME.match("migrate_ncaa_cfbd_pregame.py")
    src = (ROOT / "deploy" / "hosting" / "sp_deploy.py").read_text()
    assert "migrate_ncaa_cfbd_pregame" not in src                       # nothing to register: git finds it


def test_item_1a_the_dry_run_names_exactly_this_one_migration(tmp_path, monkeypatch, capsys):
    """A scratch origin holding every other top-level migration at the release before (v1.6.3's role), then ONE
    ordinary commit adding migrate_ncaa_cfbd_pregame.py (its real content); the clone sits on the earlier tag. The
    dry run names exactly it; the printed by-hand command runs only it."""
    import sp_common as c
    import sp_deploy

    origin, repo = tmp_path / "origin", tmp_path / "clone"
    origin.mkdir()

    def g(where, *a):
        return subprocess.run(["git", "-C", str(where), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                              check=True, capture_output=True, text=True).stdout.strip()
    g(origin, "init", "-q", "-b", "main")
    others = sorted(p.name for p in ROOT.glob("migrate_*.py") if p.name != "migrate_ncaa_cfbd_pregame.py")
    assert others
    for name in others:
        (origin / name).write_text((ROOT / name).read_text())
    g(origin, "add", "-A")
    g(origin, "commit", "-q", "-m", "the release before")
    g(origin, "tag", "v1.6.3")
    subprocess.run(["git", "clone", "-q", str(origin), str(repo)], check=True)
    g(repo, "checkout", "-q", "--detach", "v1.6.3")
    (origin / "migrate_ncaa_cfbd_pregame.py").write_text((ROOT / "migrate_ncaa_cfbd_pregame.py").read_text())
    g(origin, "add", "-A")
    g(origin, "commit", "-q", "-m", "the pregame migration")
    g(origin, "tag", "v1.6.4")
    monkeypatch.setattr(c, "REPO", repo)
    monkeypatch.setattr(c, "HOST_ENV", tmp_path / "no-host.env")
    monkeypatch.setattr(c, "_DOTENV_CACHE", None)
    monkeypatch.setenv("SP_RECEIPTS", str(tmp_path / "log" / "receipts.jsonl"))
    monkeypatch.setenv("SP_LOCK", str(tmp_path / "lib" / "db.lock"))
    before = g(repo, "rev-parse", "HEAD")
    capsys.readouterr()
    assert sp_deploy.main(["--tag", "v1.6.4", "--dry-run"]) == 0
    out = capsys.readouterr().out
    line = next(x for x in out.splitlines() if x.startswith("DRY RUN: would deploy"))
    assert re.search(r"; new migrations, in order: \['migrate_ncaa_cfbd_pregame\.py'\]", line), line
    assert "NOT determinable" not in line and "DELETES" not in line
    assert g(repo, "rev-parse", "HEAD") == before                     # a dry run moves nothing
    target = g(origin, "rev-parse", "v1.6.4")
    plan = sp_deploy.migration_plan(before, target, ["migrate_ncaa_cfbd_pregame.py"])
    assert plan["run"] == ["migrate_ncaa_cfbd_pregame.py"] and plan["forward"]
    cmd = sp_deploy.migration_command(plan["run"], target)
    assert cmd.endswith("--run-migrations migrate_ncaa_cfbd_pregame.py'")
