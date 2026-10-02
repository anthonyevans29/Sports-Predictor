"""POSTSEASON STAGE on MLB exports (architect 2026-10-01): stage comes from OUR
statsapi gameType mapping (Match.stage verbatim). R = regular; F/D/L/W =
postseason; anything else, or NULL (the host's api-sports fallback rows),
exports null — never guessed."""
import inspect

from src.walters import export


def test_mlb_stage_mapping():
    assert export.mlb_stage("R") == "regular"
    assert [export.mlb_stage(x) for x in "FDLW"] == ["postseason"] * 4
    assert export.mlb_stage(None) is None          # host fallback rows: stage NULL
    assert export.mlb_stage("S") is None           # spring training: not a stage we size
    assert export.mlb_stage("A") is None and export.mlb_stage("postseason") is None


def test_build_row_carries_stage_on_baseball_only():
    src = inspect.getsource(export._build_row)
    assert 'if is_baseball:\n        row["stage"] = mlb_stage(m.stage)' in src
    assert 'row["stage_raw"] = m.stage' in src
