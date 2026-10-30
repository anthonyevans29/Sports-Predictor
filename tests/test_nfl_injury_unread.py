"""AN EMPTY NFL INJURY LIST IS UNREAD (ARCHITECT 2026-10-11, addendum 40 item 4, #429; finding #424):

"An NFL team with no stored injury row is a list we could not read, not a team with nobody hurt. A flag we could not
look up is not a flag that is off (addendum 23, A2). Where either team's list is empty, the Desk sizes an NFL PLAY as
it sizes a QB-flagged one: half units, and the reason names the team. The page says so on that game's line. The sync
names every team whose answer was empty, in its console and in the run's receipt, and --strict does not fail on it:
the provider answered."

The finding's row: 15111 CLE at NYJ at 12:55Z read PLAY 1u × 10 with Cleveland's list empty; the host's row an hour
later, Cleveland read with 13 names (one a QB), read PLAY 0.5u × 5, QB-flagged."""
import copy
import json
from datetime import timedelta

import pytest
from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Injury, Sport, Team
from src.walters import desk_policy as dp
from tests.test_closing_runs import (  # noqa: F401  (box is a fixture)
    NOW, at, box, call_pages, mc, row, runs)

REASON = "injury list empty (Cleveland Browns): QB rule unread → half units"


def cle_at_nyj(home_count=13, away_count=0, *, qb_away=(), fair_h=0.45, p_home=0.38):
    """15111's shape: Cleveland (away) the pick, a clean exec edge, PLAY 1u when both lists are read."""
    r = row(15111, "New York Jets", p_home, fair_h=fair_h, bid=0.45, ask=0.46, comp="NFL", series="KXNFLGAME")
    r["away_team"] = "Cleveland Browns"
    if home_count is not None or away_count is not None:
        r["input_quality"] = {"book_odds": 9, "injuries": {
            "home": {"count": home_count, "qb_listed": [], "positions_unresolved": [], "synced_at": None},
            "away": {"count": away_count, "qb_listed": list(qb_away), "positions_unresolved": [],
                     "synced_at": None}}}
    return r


def desk(*rows):
    doc = dp.annotate({"sport": "nfl", "predictions": [copy.deepcopy(r) for r in rows]}, now=NOW)
    return [p["desk"] for p in doc["predictions"]], doc


def test_the_15111_row_with_clevelands_list_empty_reads_play_half_units_naming_the_team():
    (read,), _ = desk(cle_at_nyj(13, 13))
    assert (read["call"], read["units"], read["pick"]) == ("PLAY", 1, "AWAY")        # both lists read: 1u
    (d,), doc = desk(cle_at_nyj(13, 0))
    assert (d["call"], d["units"], d["pick"]) == ("PLAY", 0.5, "AWAY")
    assert REASON in d["reason"] and dp.INJURY_EMPTY_TAG in d["tags"]
    assert doc["desk_meta"]["nfl_injury_list_empty_rule"] is True
    assert doc["desk_meta"]["policy_version"] == "v1.2"            # v1.1's QB rule, law 4; v1.2: the unit (#732)
    assert d["order"]["contracts"] < read["order"]["contracts"]                       # sized at half units


def test_either_side_and_both_sides_name_their_teams():
    (d,), _ = desk(cle_at_nyj(0, 13))
    assert d["units"] == 0.5 and "injury list empty (New York Jets): QB rule unread" in d["reason"]
    (d,), _ = desk(cle_at_nyj(0, 0))
    assert d["units"] == 0.5 and "injury list empty (New York Jets and Cleveland Browns)" in d["reason"]


def test_a_row_with_a_list_on_both_sides_is_unchanged():
    with_lists, _ = desk(cle_at_nyj(13, 8))
    no_block, _ = desk(cle_at_nyj(None, None))                                         # an older file: no count
    with dp.injury_empty_rule_off():
        off, doc = desk(cle_at_nyj(13, 8))
    assert with_lists == no_block == off and doc["desk_meta"]["nfl_injury_list_empty_rule"] is False


def test_the_switch_off_restores_the_call():
    with dp.injury_empty_rule_off():
        (off,), _ = desk(cle_at_nyj(13, 0))
    (read,), _ = desk(cle_at_nyj(13, 13))
    assert off == read


def test_a_qb_flag_and_an_empty_list_are_still_half_units_not_a_quarter():
    (d,), _ = desk(cle_at_nyj(0, 13, qb_away=("Dillon Gabriel",)))
    assert d["units"] == 0.5 and "QB-flagged (Dillon Gabriel) → half units" in d["reason"] and REASON not in d["reason"]
    assert "injury list empty (New York Jets)" in d["reason"]


def test_a_quarantine_shadow_or_a_pass_is_untouched_and_no_shadow_is_resized():
    q = cle_at_nyj(13, 13, p_home=0.20, fair_h=0.45)                                   # |div| 25pp: quarantine
    (read,), _ = desk(q)
    (empty,), _ = desk({**q, "input_quality": cle_at_nyj(13, 0)["input_quality"]})
    assert read["call"] == "PASS" and read["shadow_units"] > 0 and empty == read
    p = cle_at_nyj(13, 13, p_home=0.44, fair_h=0.45)                                  # a PASS (floor)
    (read,), _ = desk(p)
    (empty,), _ = desk({**p, "input_quality": cle_at_nyj(13, 0)["input_quality"]})
    assert read["call"] == "PASS" and empty == read


def test_other_sports_are_never_read():
    r = cle_at_nyj(13, 0)
    r["competition"] = "MLB"
    a = dp.annotate({"sport": "mlb", "predictions": [copy.deepcopy(r)]}, now=NOW)["predictions"][0]["desk"]
    with dp.injury_empty_rule_off():
        b = dp.annotate({"sport": "mlb", "predictions": [copy.deepcopy(r)]}, now=NOW)["predictions"][0]["desk"]
    assert a == b


def test_the_desk_golden_holds_with_the_switch_on_and_off():
    """The parity battery's rows carry no injury count (desk_battery: qb_listed only), so the rule never fires
    there: the frozen golden holds either way."""
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import desk_battery as b
    assert all(n > 0 and not bad for _, n, bad in b.check_against_golden())
    with dp.injury_empty_rule_off():
        assert all(n > 0 and not bad for _, n, bad in b.check_against_golden())


# ------------------------------------------------------------------------------------------------ the sync --

class Fake:
    source_name = "inj_unread_fake"

    def __init__(self, by_sid):
        self.by_sid = by_sid

    def list_injuries(self, sid, season):
        v = self.by_sid[sid]
        if isinstance(v, Exception):
            raise v
        return v


def test_the_sync_names_each_empty_answer_and_strict_does_not_fail_on_it():
    from src.ingestion.service import IngestionService
    init_db()
    with session_scope() as s:
        teams = [Team(sport=Sport.NFL, name=n, external_ids={"inj_unread_fake": sid})
                 for n, sid in (("IU Jaguars", "J"), ("IU Browns", "C"), ("IU Raiders", "R"))]
        s.add_all(teams)
        s.flush()
        ids = [t.id for t in teams]
        s.add(Injury(team_id=ids[0], player_name="Old Name", source="inj_unread_fake"))
    res = IngestionService(Fake({"J": [], "C": [{"player_name": "A Back", "player_position": "RB",
                                                 "current_status": True}],
                                 "R": RuntimeError("boom")})).sync_injuries_for_teams(ids, "2026")
    assert res.empty_answers == ["IU Jaguars"]
    assert res.failed_reads == [f"team {ids[2]} (IU Raiders): fetch failed: RuntimeError"]   # only the real failure
    with session_scope() as s:                                                         # the list still replaced
        assert s.execute(select(Injury).where(Injury.team_id == ids[0])).first() is None


def test_the_console_line_and_the_closing_receipt_read_it_the_same_way(capsys):
    import cli as cli_mod
    from src.ingestion.service import SyncResult
    cli_mod._print_empty_answers("NFL", SyncResult(empty_answers=["Jacksonville Jaguars", "Las Vegas Raiders"]))
    line = capsys.readouterr().out.strip()
    assert line.startswith("EMPTY-ANSWER (NFL): 2 team(s)") and mc.EMPTY_ANSWER_MARK == cli_mod.EMPTY_ANSWER_MARK
    assert mc.empty_answers(["sync-injuries", "--competition", "NFL"], ["ok", line]) == [
        "Jacksonville Jaguars", "Las Vegas Raiders"]
    assert mc.empty_answers(["sync-odds"], [line]) == []
    cli_mod._print_empty_answers("NFL", SyncResult())
    assert capsys.readouterr().out == ""                                               # silent when none


# --------------------------------------------------------------------------------------- the closing page --

def _empty_away(box, mid=301):
    p = next(x for x in box.docs["NFL"]["predictions"] if x["match_id"] == mid)
    p["input_quality"] = {"book_odds": 9, "injuries": {
        "home": {"count": 4, "qb_listed": [], "positions_unresolved": ["U One"]},
        "away": {"count": 0, "qb_listed": [], "positions_unresolved": []}}}
    box.docs["NFL"] = dp.annotate({"sport": "nfl", "predictions": box.docs["NFL"]["predictions"]}, now=NOW)
    return p


def test_the_page_line_says_injury_list_empty_beside_b7_and_carries_the_qb_hold(box):
    _empty_away(box)
    box.tails["sync-injuries"] = ["ok", "EMPTY-ANSWER (NFL): 1 team(s) answered no injury entry, stored empty "
                                        "(read as unread): Buffalo Visitors"]
    assert mc.run("NFL", start=at(35), now=NOW) == 0
    lines = call_pages(box)[-1]["body"].splitlines()
    i = next(n for n, x in enumerate(lines) if x.startswith("Buffalo Visitors @ Buffalo · PLAY Buffalo 0.5u"))
    text = " ".join(x.strip() for x in lines[i:i + 3])
    assert "1 injured, position unresolved · injury list empty: Buffalo Visitors" in text
    assert "QB: paste to the architect before placing" in text and all(len(x) <= 100 for x in lines)
    r = runs()[-1]
    assert r["injury_lists_empty"] == ["Buffalo Visitors"]
    assert next(x for x in r["steps"] if "sync-injuries" in x["command"])["empty_answers"] == ["Buffalo Visitors"]
    assert r["desk_rows"][0]["injuries_empty"] == ["Buffalo Visitors"]


def test_the_hold_reads_the_desks_qb_tags_nfl_only():
    d = {"call": "PLAY", "tags": ["QB-flagged half units"], "exec": {"edge_pp": 6.0}}
    assert mc.hold_for(d, "NFL") == "QB: paste to the architect before placing"
    assert mc.hold_for(d, "MLB") is None
    assert mc.hold_for({**d, "tags": [dp.INJURY_EMPTY_TAG]}, "NFL") == "QB: paste to the architect before placing"
    assert mc.hold_for({**d, "tags": ["exec clears"]}, "NFL") is None
    both = mc.hold_for({**d, "exec": {"edge_pp": 2.0}}, "NFL")
    assert both == "paste to the architect before placing · QB: paste to the architect before placing"
    assert mc.hold_for({**d, "call": "PASS"}, "NFL") is None


def test_codex_base_v11_holds_the_rule_off_so_frozen_verify_files_stay_frozen():
    """Codex on #434: scripts/cockpit_desk_files.py annotates under base_v11(); cockpit_v04_verify's NFL fixture has
    count 0 on both sides, so the frozen 1u straight must not move."""
    with dp.base_v11():
        assert dp.INJURY_EMPTY_RULE["on"] is False
        (d,), doc = desk(cle_at_nyj(13, 0))
    assert d["units"] == 1 and doc["desk_meta"]["nfl_injury_list_empty_rule"] is False
    assert dp.INJURY_EMPTY_RULE["on"] is True                                          # restored


def test_codex_a_strict_failure_still_ends_with_the_empty_answer_line(capsys):
    """Codex on #434: with four or more failed reads the strict lines pushed EMPTY-ANSWER out of the 5-line step
    tail; it is now printed again as the last line, and the closing parser keeps each team once."""
    import cli as cli_mod
    from src.ingestion.service import SyncResult
    res = SyncResult(empty_answers=["Jacksonville Jaguars"], failed_reads=[f"team {i}: fetch failed" for i in range(6)])
    cli_mod._print_empty_answers("NFL", res)
    with pytest.raises(SystemExit):
        cli_mod._strict_injuries_fail("NFL", res.failed_reads, res)
    lines = [x for x in capsys.readouterr().out.splitlines() if x.strip()]
    tail = lines[-5:]                                                                 # sp_run.TAIL
    assert tail[-1].startswith("EMPTY-ANSWER (NFL)")
    assert mc.empty_answers(["sync-injuries"], lines) == ["Jacksonville Jaguars"]      # once, not twice
    assert mc.empty_answers(["sync-injuries"], tail) == ["Jacksonville Jaguars"]
