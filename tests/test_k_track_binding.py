"""THE K-TRACK LABEL READS BINDING (ARCHITECT 2026-10-20 09:59 ET, addendum 146 item 1(vi)), verbatim: "The exports'
label "K-track: informational until the executable-edge ruling" becomes "K-track: binding (ARCHITECT 2026-10-20,
addendum 146 item 1)" wherever it is written (fixtures, predictions, shadow exports, the Cockpit's copy). Wording only;
one PR with (v)."

Every writer takes the label from venue.kalshi_exec() (`k_track`); a shadow row is the fixtures row plus its own keys,
so it carries the fixtures row's label. The two-sided fixtures row is built on a throwaway SQLite file (iso_db)."""
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.walters import venue
from tests.test_record_vs_close import iso_db  # noqa: F401  (a fixture: a throwaway SQLite, cwd = tmp_path)

ROOT = Path(__file__).resolve().parent.parent
BINDING = "K-track: binding (ARCHITECT 2026-10-20, addendum 146 item 1)"


def test_the_label_reads_binding_word_for_word():
    assert venue.K_TRACK_NOTE == BINDING
    assert venue.kalshi_exec(0.53, 0.55)["k_track"] == BINDING
    assert "k_track" not in venue.KALSHI_EXEC_NULL               # a row with no two-sided set carries no label


def test_no_source_file_and_not_the_cockpit_says_informational_any_more():
    old = re.compile(r"informational until the executable-edge ruling", re.IGNORECASE)
    files = sorted((ROOT / "src").rglob("*.py")) + [ROOT / "tools" / "cockpit.html"]
    hits = [str(p.relative_to(ROOT)) for p in files
            if old.search(p.read_text(encoding="utf-8")) or "INFORMATIONAL ONLY: no sizing" in p.read_text(
                encoding="utf-8")]
    assert hits == []
    cockpit = (ROOT / "tools" / "cockpit.html").read_text(encoding="utf-8")
    assert "// BINDING since ARCHITECT 2026-10-20 (addendum 146 item 1(i)): desk.exec.edge_pp" in cockpit


def _nhl_game_two_sided():
    """One NHL game tomorrow with a two-sided Kalshi set (HOME and AWAY legs, both quotes stored)."""
    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, OddsSnapshot, Sport, Team
    from src.timeutil import utc_now_naive
    kick = utc_now_naive().replace(microsecond=0) + timedelta(days=1)
    with session_scope() as s:
        c = Competition(sport=Sport.NHL, code="NHL", name="NHL", area="X", type="LEAGUE")
        h, a = Team(sport=Sport.NHL, name="Kappa Kodiaks"), Team(sport=Sport.NHL, name="Omega Owls")
        s.add_all([c, h, a])
        s.flush()
        m = Match(sport=Sport.NHL, competition_id=c.id, season="2026", utc_date=kick, status=MatchStatus.SCHEDULED,
                  home_team_id=h.id, away_team_id=a.id)
        s.add(m)
        s.flush()
        for sel, bid, ask in (("HOME", 0.53, 0.55), ("AWAY", 0.45, 0.47)):
            s.add(OddsSnapshot(match_id=m.id, market="ML", selection=sel, devig_prob=(bid + ask) / 2,
                               captured_at=kick - timedelta(hours=2), source="kalshi", yes_bid=bid, yes_ask=ask))
        return m.id


@pytest.mark.usefixtures("iso_db")
def test_a_shadow_row_built_from_a_two_sided_fixtures_row_carries_the_binding_label():
    from src.db.database import session_scope
    from src.db.schema import Match
    from src.walters import soccer_expansion
    from src.walters.export import _fixture_row
    mid = _nhl_game_two_sided()
    with session_scope() as s:
        fx = _fixture_row(s, s.get(Match, mid), "NHL", Counter(), Counter())
    assert fx["input_quality"]["kalshi"] == "two_sided" and fx["k_track"] == venue.K_TRACK_NOTE
    # nhl_shadow / intl_shadow / ncaa_shadow: the fixtures row, updated with the shadow's own keys (row.update)
    row = dict(fx)
    row.update({"engine": "model_shadow", "model_version": "x", "gate_verdict": "FAILED",
                "prediction": {"home_win_prob": 0.5, "away_win_prob": 0.5, "top_pick": "home_win"}})
    assert row["k_track"] == BINDING
    # soccer_expansion.shadow_row: {**fixture_row, ...} (pure)
    pred = SimpleNamespace(p_home=0.4, p_draw=0.3, p_away=0.3)
    assert soccer_expansion.shadow_row(fx, pred, "v22", "declared", "SA")["k_track"] == BINDING
    assert datetime.fromisoformat(fx["utc_date"]) > datetime(2026, 1, 1)
