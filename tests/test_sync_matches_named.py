"""sync-matches --match-ids: the closing runs' schedule read (ARCHITECT 2026-10-09, addendum 23 A1; A1 as amended,
addendum 25 item 2(i): NFL, SOCCER and MLB all read by date with the covered games named). Moved here from
tests/test_refresh_by_id.py when that file returned to what #378 merged (addendum 25 2(i)); the helpers are that
file's own. Throwaway DB only (tests/conftest.py); the provider is a fake adapter, no network."""
from click.testing import CliRunner

from tests.test_refresh_by_id import DAY3, FakeAdapter, _isolated, _match, _nm  # noqa: F401 (_isolated: autouse)


def test_a1_sync_matches_match_ids_exits_1_unless_the_answer_held_every_named_game(monkeypatch, _isolated):
    """A1 (addendum 23): SOCCER's and MLB's schedule read "stay sync-matches by date, with an opt-in that names the
    covered games and exits non-zero unless the provider's answer held every one of them. Every default is
    unchanged." NFL's too, A1 as amended (addendum 25 2(i)). The test as it stood in tests/test_refresh_by_id.py."""
    import cli
    code = "RBX"
    held = _match(code, "9801", "h25", "a25", DAY3)
    dropped = _match(code, "9802", "h26", "a26", DAY3)
    _isolated.extend([held, dropped])
    day = DAY3.strftime("%Y-%m-%d")
    fake = FakeAdapter(listing=[_nm(code, "9801", "rbi-h25", "rbi-a25", DAY3)])     # the listing omits 9802
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda c: fake)
    monkeypatch.setattr(cli, "_mlb_fallback", lambda c: False)
    base = ["sync-matches", "--competition", code, "--season", "2026", "--date-from", day, "--date-to", day]
    res = CliRunner().invoke(cli.cli, base)
    assert res.exit_code == 0 and "STRICT" not in res.output                         # default: unchanged
    res = CliRunner().invoke(cli.cli, [*base, "--match-ids", str(held)])
    assert res.exit_code == 0 and "held all 1 named game(s)" in res.output, res.output
    res = CliRunner().invoke(cli.cli, [*base, "--match-ids", f"{held},{dropped}"])
    assert res.exit_code == 1 and f"✗ STRICT: 1 of 2 named game(s) not in the provider's answer" in res.output
    assert f"match {dropped}" in res.output
