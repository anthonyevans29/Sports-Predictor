"""#105 item (1) (ARCHITECT 2026-10-30 08:10 ET): the leaders-order read of the probe's kept payloads. Synthetic
payloads under tmp_path only; no network, nothing written beside them."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("lor", ROOT / "scripts" / "nhl_leaders_order_read.py")
lor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lor)


def _landing(home, away):
    side = lambda ids: {"leaders": [{"playerId": i, "name": {"default": f"G{i}"}} for i in ids]}
    return {"gameState": "FUT", "matchup": {"goalieComparison": {"homeTeam": side(home), "awayTeam": side(away)}}}


def _box(home, away):
    return {"playerByGameStats": {"homeTeam": {"goalies": [{"playerId": i, "toi": t} for i, t in home]},
                                  "awayTeam": {"goalies": [{"playerId": i, "toi": t} for i, t in away]}}}


def _write(d: Path, gid: int, name: str, obj):
    (d / f"{gid}_{name}.json").write_text(obj if isinstance(obj, str) else json.dumps(obj))


def test_the_order_is_read_at_every_poll_and_a_flip_is_named(tmp_path, capsys):
    for p in lor.POLLS:
        _write(tmp_path, 7, f"landing_{p}", _landing([1, 2] if p in ("T-120", "T-90") else [2, 1], [3, 4]))
    _write(tmp_path, 7, "boxscore_T+20", _box([(2, "18:31"), (1, "00:00")], [(3, "19:02"), (4, "00:00")]))
    assert lor.main([str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "7 home · eventual (T+20 boxscore, toi > 0): 2 ?" in out               # this boxscore carries no name
    assert "    T-120: leaders (2) [0] 1 G1, 2 G2" in out and "    T-60: leaders (2) [0] 2 G2, 1 G1" in out
    assert "flips of leaders[0] across the kept polls: 1 · T-90->T-60 (1->2)" in out
    assert "  T-35 (the cutoff): read 2 · agrees 2 · differs 0 · eventual unread 0 · hit rate 2/2 (100%)" in out
    assert "  T-120: read 2 · agrees 1 · differs 1 · eventual unread 0 · hit rate 1/2 (50%)" in out
    assert "PROBE (the probe's own asserted() on 7_landing_T-35.json): away kind listed" in out


def test_an_eventual_starter_is_read_only_when_exactly_one_goalie_played(tmp_path, capsys):
    """Two goalies with toi > 0 (a pull before T+20), none, or no boxscore kept: unread, never guessed."""
    _write(tmp_path, 8, "landing_T-35", _landing([1, 2], [3, 4]))
    _write(tmp_path, 8, "boxscore_T+20", _box([(1, "10:00"), (2, "08:31")], [(3, "00:00"), (4, "00:00")]))
    _write(tmp_path, 9, "landing_T-35", _landing([5], [6]))
    lor.main([str(tmp_path)])
    out = capsys.readouterr().out
    assert "8 home · eventual (T+20 boxscore, toi > 0): unread (2 goalies with toi > 0" in out
    assert "8 away · eventual (T+20 boxscore, toi > 0): unread (no goalie with toi > 0)" in out
    assert "9 home · eventual (T+20 boxscore, toi > 0): unread (no T+20 boxscore kept)" in out
    assert "  T-35 (the cutoff): read 4 · agrees 0 · differs 0 · eventual unread 4 · hit rate: none judged" in out


def test_a_missing_or_torn_payload_or_another_shape_is_said_never_filled(tmp_path, capsys):
    _write(tmp_path, 10, "landing_T-35", "{torn")
    _write(tmp_path, 10, "landing_T-30", {"matchup": {"skaterComparison": {}}})
    (tmp_path / "notes.json").write_text("{}")
    lor.main([str(tmp_path), str(tmp_path / "absent")])
    out = capsys.readouterr().out
    assert "1 file(s) not of the probe's name form" in out
    assert "    T-35: no matchup.goalieComparison.homeTeam.leaders list" in out
    assert "    T-30: no matchup.goalieComparison.homeTeam.leaders list" in out
    assert "    T-120: no landing payload kept" in out
    assert f"DIR {tmp_path / 'absent'} · not a directory" in out
    assert "landing: no path naming 'goalie'" in out


def test_the_shape_is_printed_before_any_reading_rests_on_it(tmp_path, capsys):
    _write(tmp_path, 11, "landing_T-120", _landing([1, 2], [3]))
    _write(tmp_path, 11, "right-rail_T-120", {"seasonSeries": [], "goalieLeaders": {"x": 1}})
    lor.main([str(tmp_path)])
    out = capsys.readouterr().out
    assert out.index("SHAPE") < out.index("11 away · eventual")
    assert ("landing matchup.goalieComparison.homeTeam.leaders: list of 2, first member keys ['name', 'playerId']"
            in out)
    assert "right-rail goalieLeaders: object, keys ['x']" in out


def test_no_directory_given_is_a_usage_exit():
    assert lor.main([]) == 2
