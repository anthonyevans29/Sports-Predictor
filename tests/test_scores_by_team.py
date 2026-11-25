"""SCORES BY TEAM (ARCHITECT 2026-11-08, addendum 292 item 3; #876). Item 3(f), verbatim: "tests: the reversed listing →
scores by team, result H↔A, the count and the listed id; the mismatched pair → refused, the row byte-identical, the
count; the same pair → today's behaviour unchanged; one soccer row with _ht and _90 reversed".

The cause (addendum 292 item 2): "src/ingestion/service.py `_apply_match_updates` writes match.home_score =
nm.home_score and the mirror, and the five sibling fields, by position". The two rows of item 1 (36454, 36753) are
modelled here: the stored pair is the listing's reverse, the provider's scores are right.

Throwaway DB only (tests/conftest.py); the providers are fake adapters, no network."""
import itertools
from datetime import datetime, timedelta

import pytest
from click.testing import CliRunner
from sqlalchemy import select, text

from src.adapters.normalized import NormalizedMatch
from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Result, Sport, Team
from src.ingestion import refresh_by_id as rbi
from src.ingestion import service as svc
from src.ingestion.match_dedupe import TWIN_H
from src.ingestion.placeholder import PLACEHOLDER_RESOLVE_H, PLACEHOLDER_TEAM_ID, is_placeholder_team
from src.ingestion.score_orientation import MISMATCH, REVERSED, SAME, orientation, placeholder_fill, scores_by_team
from src.ingestion.service import IngestionService
from src.timeutil import utc_now_naive

AF = "api_american_football"
SOC = "api_football"
_seq = itertools.count(1)
KICK = datetime(2026, 10, 31, 19, 45)                      # 36454's kickoff as the provider serves it (item 1)


class Listing:
    """list_matches = the listing; get_game = the answer by id (refresh_by_id)."""

    def __init__(self, source, listing=(), by_id=None):
        self.source_name = source
        self.listing, self.by_id = list(listing), dict(by_id or {})

    def list_matches(self, code, season=None, date_from=None, date_to=None):
        return list(self.listing)

    def get_game(self, sid, code="NCAA"):
        return (True, self.by_id[sid]) if sid in self.by_id else (False, None)


def _comp(s, code, sport):
    c = s.execute(select(Competition).where(Competition.code == code)).scalar_one_or_none()
    if c is None:
        c = Competition(sport=sport, code=code, name=code, area="x", type="LEAGUE")
        s.add(c)
        s.flush()
    return c


def _teams(sport, source, n=2):
    """n new team rows of `sport` with their provider ids; returns [(team id, provider id)]."""
    init_db()
    out = []
    with session_scope() as s:
        for _ in range(n):
            k = next(_seq)
            pid = f"sbt-{sport.value}-{k}-{utc_now_naive():%H%M%S%f}"
            t = Team(sport=sport, name=f"SBT {pid}", external_ids={source: pid})
            s.add(t)
            s.flush()
            out.append((t.id, pid))
    return out


def _stored(code, sport, source, sid, home, away, when=KICK, status=MatchStatus.SCHEDULED, ext=None, **scores):
    init_db()
    with session_scope() as s:
        c = _comp(s, code, sport)
        m = Match(sport=sport, competition_id=c.id, season="2026", utc_date=when, status=status,
                  home_team_id=home, away_team_id=away, external_ids=ext if ext is not None else {source: sid},
                  **scores)
        s.add(m)
        s.flush()
        return m.id


def _nm(code, sport, source, sid, home_pid, away_pid, when=KICK, status=MatchStatus.FINISHED, **scores):
    return NormalizedMatch(sport=sport, competition_code=code, season="2026", utc_date=when, status=status,
                           home_team_source_id=home_pid, away_team_source_id=away_pid, source=source, source_id=sid,
                           status_raw="FT" if status == MatchStatus.FINISHED else None, **scores)


def _raw(mid):
    """Every column of the stored row, as SQLite holds it (the byte-identical check)."""
    with session_scope() as s:
        return dict(s.execute(text("SELECT * FROM matches WHERE id = :i"), {"i": mid}).mappings().one())


def _sync(code, source, listing, **kw):
    return IngestionService(Listing(source, listing)).sync_matches(code, season="2026", **kw)


# ---------------------------------------------------------------------------- the helper, pure


def test_the_helper_decides_same_reversed_and_neither():
    assert orientation((1, 2), (1, 2)) == SAME
    assert orientation((1, 2), (2, 1)) == REVERSED
    assert orientation((1, 2), (1, 3)) == MISMATCH and orientation((1, 2), (3, 4)) == MISMATCH
    assert orientation((1, 2), (None, 2)) == MISMATCH and orientation((1, 1), (1, 1)) == SAME
    v = {"home_score": 25, "away_score": 49, "home_score_ht": 7, "away_score_ht": 21, "home_score_90": 24,
         "away_score_90": 42, "full_time_result": Result.AWAY}
    assert scores_by_team((1, 2), (1, 2), v) == (SAME, v)
    verdict, out = scores_by_team((2, 1), (1, 2), v)
    assert verdict == REVERSED and out == {"home_score": 49, "away_score": 25, "home_score_ht": 21, "away_score_ht": 7,
                                           "home_score_90": 42, "away_score_90": 24,
                                           "full_time_result": Result.HOME}
    assert scores_by_team((2, 1), (1, 2), {"full_time_result": Result.DRAW})[1] == {"full_time_result": Result.DRAW}
    assert scores_by_team((2, 1), (1, 2), {"home_score": 3})[1] == {"home_score": None, "away_score": 3}
    assert scores_by_team((1, 2), (1, 3), v) == (MISMATCH, None)


# ---------------------------------------------------------------------------- sync_matches: update by id


def test_a_reversed_listing_writes_the_scores_by_team_and_the_result_h_a_and_lists_the_id():
    """36454 (item 1): stored home Utah / away Cincinnati; the provider (id 18216) serves home Cincinnati 25, away Utah
    49, FT. Today's positional write makes our row say Cincinnati won; by team it reads Utah 49, Cincinnati 25."""
    (utah, utah_p), (cin, cin_p) = _teams(Sport.NFL, AF)
    mid = _stored("SBTN", Sport.NFL, AF, "sbt-18216", utah, cin)
    res = _sync("SBTN", AF, [_nm("SBTN", Sport.NFL, AF, "sbt-18216", cin_p, utah_p, home_score=25, away_score=49,
                                 full_time_result=Result.AWAY)])
    row = _raw(mid)
    assert (row["home_score"], row["away_score"]) == (49, 25)            # Utah (our home) 49, Cincinnati 25
    with session_scope() as s:
        m = s.get(Match, mid)
        assert m.full_time_result == Result.HOME                         # Utah won: H in OUR orientation
        assert (m.home_team_id, m.away_team_id) == (utah, cin)           # item 3(d): the orientation is NOT flipped
        assert m.status == MatchStatus.FINISHED and m.utc_date == KICK and m.status_raw == "FT"
    assert res.orientation_reversed == [mid] and res.teams_mismatch_refused == []
    assert res.updated == 1 and res.created == 0


def _but_ext(row):
    return {k: v for k, v in row.items() if k != "external_ids"}


def test_a_mismatched_pair_is_refused_every_column_but_the_key_untouched_and_counted():
    """Addendum 297 C(ii): the scores path is unchanged (no score, kickoff or status written); the one write is the
    key's third value, `mismatch`."""
    (h, _hp), (a, ap), (_x, xp) = _teams(Sport.NFL, AF, 3)
    mid = _stored("SBTN", Sport.NFL, AF, "sbt-mis-1", h, a, home_score=10, away_score=3,
                  full_time_result=Result.HOME, status=MatchStatus.FINISHED)
    before = _raw(mid)
    res = _sync("SBTN", AF, [_nm("SBTN", Sport.NFL, AF, "sbt-mis-1", xp, ap, when=KICK + timedelta(hours=2),
                                 home_score=0, away_score=44, full_time_result=Result.AWAY)])
    after = _raw(mid)
    assert _but_ext(after) == _but_ext(before)                           # every other column, untouched
    import json
    assert json.loads(after["external_ids"]) == {AF: "sbt-mis-1", "provider_orientation": "mismatch"}
    assert res.teams_mismatch_refused == [mid] and res.orientation_reversed == []
    assert res.updated == 0 and res.created == 0 and res.skipped == 1 and res.skipped_ids == []


def test_the_same_pair_keeps_todays_writes():
    (h, hp), (a, ap) = _teams(Sport.NFL, AF)
    mid = _stored("SBTN", Sport.NFL, AF, "sbt-same-1", h, a)
    res = _sync("SBTN", AF, [_nm("SBTN", Sport.NFL, AF, "sbt-same-1", hp, ap, when=KICK + timedelta(minutes=15),
                                 home_score=13, away_score=31, full_time_result=Result.AWAY)])
    row = _raw(mid)
    assert (row["home_score"], row["away_score"]) == (13, 31)
    with session_scope() as s:
        m = s.get(Match, mid)
        assert m.full_time_result == Result.AWAY and m.utc_date == KICK + timedelta(minutes=15)
    assert res.orientation_reversed == [] and res.teams_mismatch_refused == [] and res.updated == 1


def test_a_soccer_row_reversed_takes_ht_and_90_by_team():
    (h, hp), (a, ap) = _teams(Sport.SOCCER, SOC)
    mid = _stored("SBTS", Sport.SOCCER, SOC, "sbt-soc-1", h, a)
    # every pair asymmetric, so a pair left unswapped cannot pass (a symmetric 2-2 reads the same either way)
    res = _sync("SBTS", SOC, [_nm("SBTS", Sport.SOCCER, SOC, "sbt-soc-1", ap, hp, home_score=4, away_score=2,
                                  home_score_ht=1, away_score_ht=0, home_score_90=3, away_score_90=1,
                                  full_time_result=Result.HOME)])
    row = _raw(mid)
    assert (row["home_score"], row["away_score"]) == (2, 4)
    assert (row["home_score_ht"], row["away_score_ht"]) == (0, 1)
    assert (row["home_score_90"], row["away_score_90"]) == (1, 3)
    with session_scope() as s:
        assert s.get(Match, mid).full_time_result == Result.AWAY
    assert res.orientation_reversed == [mid]


def test_a_reversed_draw_keeps_d():
    (h, hp), (a, ap) = _teams(Sport.SOCCER, SOC)
    mid = _stored("SBTS", Sport.SOCCER, SOC, "sbt-soc-d", h, a)
    _sync("SBTS", SOC, [_nm("SBTS", Sport.SOCCER, SOC, "sbt-soc-d", ap, hp, home_score=1, away_score=1,
                            full_time_result=Result.DRAW)])
    with session_scope() as s:
        m = s.get(Match, mid)
        assert (m.home_score, m.away_score, m.full_time_result) == (1, 1, Result.DRAW)


@pytest.mark.parametrize("source", [AF, SOC])
def test_a_repeated_id_in_one_listing_lists_the_new_rows_id_not_none(source):
    """#884 review (Codex round 1): one response carrying the same new id twice. The first creates the row (cached,
    unflushed: SessionLocal has autoflush=False); a reversed or mismatched second must list that row's id, never None.
    The create itself is counted as before (created 1)."""
    sport = Sport.NFL if source == AF else Sport.SOCCER
    (h, hp), (a, ap), (_x, xp) = _teams(sport, source, 3)
    when = KICK + timedelta(days=9)
    code = "SBTD" if source == AF else "SBTDS"
    with session_scope() as s:
        _comp(s, code, sport)
    res = _sync(code, source, [
        _nm(code, sport, source, f"sbt-dup-{source}", hp, ap, when=when, home_score=2, away_score=1),
        _nm(code, sport, source, f"sbt-dup-{source}", ap, hp, when=when, home_score=1, away_score=2),   # reversed
        _nm(code, sport, source, f"sbt-dup-{source}", xp, ap, when=when, home_score=5, away_score=5)])  # neither
    with session_scope() as s:
        mid = s.execute(select(Match.id).where(Match.home_team_id == h, Match.away_team_id == a)).scalar_one()
        m = s.get(Match, mid)
        assert (m.home_score, m.away_score) == (2, 1) and (m.home_team_id, m.away_team_id) == (h, a)
    assert res.orientation_reversed == [mid] and res.teams_mismatch_refused == [mid]
    assert res.created == 1 and res.updated == 1 and res.skipped == 1


def test_the_cli_receipt_prints_both_counts_with_the_ids(monkeypatch):
    import cli
    (h, hp), (a, ap), (_x, xp) = _teams(Sport.NFL, AF, 3)
    rev = _stored("SBTC", Sport.NFL, AF, "sbt-cli-1", h, a)
    mis = _stored("SBTC", Sport.NFL, AF, "sbt-cli-2", h, a, when=KICK + timedelta(days=7))
    fake = Listing(AF, [_nm("SBTC", Sport.NFL, AF, "sbt-cli-1", ap, hp, home_score=13, away_score=31),
                        _nm("SBTC", Sport.NFL, AF, "sbt-cli-2", xp, ap, when=KICK + timedelta(days=7))])
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda c: fake)
    monkeypatch.setattr(cli, "_mlb_fallback", lambda c: False)
    res = CliRunner().invoke(cli.cli, ["sync-matches", "--competition", "SBTC", "--season", "2026"])
    assert res.exit_code == 0, res.output
    assert f"orientation_reversed 1: {rev} · teams_mismatch_refused 1: {mis}" in res.output.splitlines()


def test_strict_names_a_refused_row_as_refused_not_as_absent_from_the_answer(monkeypatch):
    """--match-ids: a named row whose listing was REFUSED (neither pair) was in the provider's answer; the STRICT line
    says it was refused, with its own label, and the exit stays 1."""
    import cli
    (h, hp), (a, ap), (_x, xp) = _teams(Sport.NFL, AF, 3)
    mis = _stored("SBTK", Sport.NFL, AF, "sbt-strict-1", h, a)
    gone = _stored("SBTK", Sport.NFL, AF, "sbt-strict-2", h, a, when=KICK + timedelta(days=7))
    fake = Listing(AF, [_nm("SBTK", Sport.NFL, AF, "sbt-strict-1", xp, ap)])
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda c: fake)
    monkeypatch.setattr(cli, "_mlb_fallback", lambda c: False)
    res = CliRunner().invoke(cli.cli, ["sync-matches", "--competition", "SBTK", "--season", "2026",
                                       "--match-ids", f"{mis},{gone}"])
    assert res.exit_code == 1, res.output
    lines = res.output.splitlines()
    assert any(x.startswith("✗ STRICT: 1 of 2 named game(s) not in the provider's answer") and x.endswith(f"match {gone}")
               for x in lines), res.output
    assert (f"✗ STRICT: 1 of 2 named game(s) REFUSED (the listing's teams are neither the stored pair nor its "
            f"reverse; scores, kickoff and status untouched; provider_orientation mismatch written): match {mis}") in lines, res.output


def test_the_admin_sync_job_carries_both_counts(monkeypatch):
    from src.web.routes import admin
    (h, hp), (a, ap) = _teams(Sport.NFL, AF)
    rev = _stored("SBTA", Sport.NFL, AF, "sbt-adm-1", h, a)
    fake = Listing(AF, [_nm("SBTA", Sport.NFL, AF, "sbt-adm-1", ap, hp, home_score=13, away_score=31)])
    monkeypatch.setattr(admin, "_adapter_for_competition", lambda c: fake)
    out = admin._job_sync_matches(competition_code="SBTA", season="2026", seasons=0)
    assert out.endswith(f"orientation_reversed 1: {rev} · teams_mismatch_refused 0"), out


def test_the_tennis_re_read_prints_its_own_counts(monkeypatch, capsys):
    """cli._tennis_reread runs a second sync_matches over the listing already read; its counts are printed too."""
    import cli
    from types import SimpleNamespace as NS
    from datetime import date
    from src.adapters.kalshi_tennis import SOURCE
    (h, _hp), (a, _ap) = _teams(Sport.NFL, SOURCE)
    mid = _stored("SBTT", Sport.NFL, SOURCE, "sbt-tr-1", h, a)
    done = svc.SyncResult(updated=1)
    done.teams_mismatch_refused.append(mid)

    class Svc:
        adapter = NS(events=None)

        def sync_matches(self, code, season=None):
            return done
    lst = NS(fixtures=[NS(event="sbt-tr-1", day=date(2026, 12, 29),
                          settlement=NS(status=MatchStatus.SCHEDULED))])
    try:
        cli._tennis_reread(Svc(), "SBTT", "2026", lst, "2026-12-31")
        out = capsys.readouterr().out.splitlines()
        assert f"  SBTT re-read: orientation_reversed 0 · teams_mismatch_refused 1: {mid}" in out, out
    finally:
        # the row carries the tennis source key: removed, so the tennis suites (which read every kalshi_tennis row in
        # the shared test DB) never see it, whatever the test order
        with session_scope() as s:
            s.delete(s.get(Match, mid))


def test_the_cli_receipt_prints_zero_counts(monkeypatch):
    import cli
    (h, hp), (a, ap) = _teams(Sport.NFL, AF)
    _stored("SBTZ", Sport.NFL, AF, "sbt-zero-1", h, a)
    fake = Listing(AF, [_nm("SBTZ", Sport.NFL, AF, "sbt-zero-1", hp, ap)])
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda c: fake)
    monkeypatch.setattr(cli, "_mlb_fallback", lambda c: False)
    res = CliRunner().invoke(cli.cli, ["sync-matches", "--competition", "SBTZ", "--season", "2026"])
    assert res.exit_code == 0, res.output
    assert "orientation_reversed 0 · teams_mismatch_refused 0" in res.output


# ---------------------------------------------------------------------------- sync_matches: the re-key branch


def test_a_rekey_by_history_with_the_pair_reversed_writes_by_team_and_rekeys():
    """The re-key's history branch finds the row by an id it carried before, whatever teams the listing carries."""
    (h, hp), (a, ap) = _teams(Sport.NFL, AF)
    mid = _stored("SBTR", Sport.NFL, AF, None, h, a,
                  ext={AF: "sbt-rk-old", f"{AF}_prev": ["sbt-rk-new"]})
    res = _sync("SBTR", AF, [_nm("SBTR", Sport.NFL, AF, "sbt-rk-new", ap, hp, home_score=13, away_score=31)])
    row = _raw(mid)
    assert (row["home_score"], row["away_score"]) == (31, 13)
    with session_scope() as s:
        m = s.get(Match, mid)
        assert m.external_ids[AF] == "sbt-rk-new" and (m.home_team_id, m.away_team_id) == (h, a)
    assert res.rekeyed == 1 and res.orientation_reversed == [mid]


def test_a_rekey_by_history_with_neither_pair_is_refused_the_row_byte_identical():
    (h, _hp), (a, ap), (_x, xp) = _teams(Sport.NFL, AF, 3)
    mid = _stored("SBTR", Sport.NFL, AF, None, h, a, when=KICK + timedelta(days=3),
                  ext={AF: "sbt-rk-old2", f"{AF}_prev": ["sbt-rk-new2"]})
    before = _raw(mid)
    res = _sync("SBTR", AF, [_nm("SBTR", Sport.NFL, AF, "sbt-rk-new2", xp, ap, when=KICK + timedelta(days=3),
                                 home_score=13, away_score=31)])
    assert _raw(mid) == before
    assert res.rekeyed == 0 and res.created == 0 and res.teams_mismatch_refused == [mid]


def test_a_refused_history_rekey_releases_its_claim_so_a_valid_listing_rekeys_the_row():
    """#884 review (Codex round 1): the history branch claims the row's current id before the team check runs. A
    refusal there re-keys nothing, so it must leave no claim: a later valid listing for the same stored row in the same
    sync takes it (its score and provider id written), never 'already re-keyed'."""
    (h, hp), (a, ap), (_x, xp) = _teams(Sport.NFL, AF, 3)
    when = KICK + timedelta(days=7)
    mid = _stored("SBTR", Sport.NFL, AF, None, h, a, when=when,
                  ext={AF: "sbt-cl-old", f"{AF}_prev": ["sbt-cl-reused"]})
    res = _sync("SBTR", AF, [
        _nm("SBTR", Sport.NFL, AF, "sbt-cl-reused", xp, ap, when=when, home_score=0, away_score=9),   # neither pair
        _nm("SBTR", Sport.NFL, AF, "sbt-cl-new", hp, ap, when=when + timedelta(hours=1), home_score=21,
            away_score=14)])                                                                     # the natural key
    row = _raw(mid)
    assert (row["home_score"], row["away_score"]) == (21, 14)
    with session_scope() as s:
        assert s.get(Match, mid).external_ids[AF] == "sbt-cl-new"
    assert res.teams_mismatch_refused == [mid] and res.rekeyed == 1 and res.rekey_refused == 0
    assert res.created == 0 and res.updated == 1


def test_a_natural_key_rekey_takes_the_same_pair_as_today():
    (h, hp), (a, ap) = _teams(Sport.NFL, AF)
    mid = _stored("SBTR", Sport.NFL, AF, "sbt-nk-old", h, a, when=KICK + timedelta(days=5))
    res = _sync("SBTR", AF, [_nm("SBTR", Sport.NFL, AF, "sbt-nk-new", hp, ap, when=KICK + timedelta(days=5, hours=1),
                                 home_score=24, away_score=17)])
    row = _raw(mid)
    assert (row["home_score"], row["away_score"]) == (24, 17)
    assert res.rekeyed == 1 and res.orientation_reversed == [] and res.teams_mismatch_refused == []


def test_a_placeholder_kickoff_row_keeps_its_own_path():
    """The NCAA placeholder KICKOFF (04:00Z, src/ingestion/placeholder.py) on a row whose teams are real keeps its own
    path: its re-key window takes the same pair only, so the helper reads SAME and nothing changes. The provider's
    placeholder TEAM (provider id 345) is the fill's rule (the section at the end of this file), which supersedes the
    premise "never a team ... no TBD team row exists" (BACKLOG.md:3383; ARCHITECT 2026-11-24, addendum 500 Q1 and
    Q10)."""
    (h, hp), (a, ap) = _teams(Sport.NFL, AF)
    ph = datetime(2026, 11, 14, 4, 0)
    mid = _stored("NCAA", Sport.NFL, AF, "sbt-ph-old", h, a, when=ph)
    res = _sync("NCAA", AF, [_nm("NCAA", Sport.NFL, AF, "sbt-ph-new", hp, ap, when=ph + timedelta(hours=16),
                                 status=MatchStatus.SCHEDULED)])
    with session_scope() as s:
        m = s.get(Match, mid)
        assert m.external_ids[AF] == "sbt-ph-new" and m.utc_date == ph + timedelta(hours=16)
    assert res.rekeyed == 1 and res.orientation_reversed == [] and res.teams_mismatch_refused == []


# ---------------------------------------------------------------------------- refresh_by_id


@pytest.fixture
def _rbi_quiet(monkeypatch):
    monkeypatch.setattr(svc, "_odds_sleep", lambda s: None)


def _rbi_rows(code):
    """Three stored SCHEDULED rows in the refresh window: reversed, mismatched, same."""
    day = datetime.combine(utc_now_naive().date() + timedelta(days=2), datetime.min.time()) + timedelta(hours=20)
    (h1, h1p), (a1, a1p), (h2, _h2p), (a2, a2p), (h3, h3p), (a3, a3p), (_x, xp) = _teams(Sport.NFL, AF, 7)
    rows = {"rev": _stored(code, Sport.NFL, AF, f"sbt-rbi-{code}-1", h1, a1, when=day),
            "mis": _stored(code, Sport.NFL, AF, f"sbt-rbi-{code}-2", h2, a2, when=day),
            "same": _stored(code, Sport.NFL, AF, f"sbt-rbi-{code}-3", h3, a3, when=day)}
    later = day + timedelta(minutes=30)
    by_id = {f"sbt-rbi-{code}-1": _nm(code, Sport.NFL, AF, f"sbt-rbi-{code}-1", a1p, h1p, when=later,
                                      home_score=13, away_score=31),
             f"sbt-rbi-{code}-2": _nm(code, Sport.NFL, AF, f"sbt-rbi-{code}-2", xp, a2p, when=later,
                                      home_score=7, away_score=0),
             f"sbt-rbi-{code}-3": _nm(code, Sport.NFL, AF, f"sbt-rbi-{code}-3", h3p, a3p, when=later,
                                      home_score=24, away_score=17)}
    return rows, by_id, later


def test_refresh_by_id_writes_a_reversed_answer_by_team_refuses_neither_and_keeps_the_same_pair(_rbi_quiet):
    rows, by_id, later = _rbi_rows("SBTB")
    before = _raw(rows["mis"])
    r = rbi.refresh("SBTB", Listing(AF, by_id=by_id), days=7)
    rev = _raw(rows["rev"])
    assert (rev["home_score"], rev["away_score"]) == (31, 13)              # by team, the orientation kept
    with session_scope() as s:
        m = s.get(Match, rows["rev"])
        assert m.status == MatchStatus.FINISHED and m.utc_date == later    # the kickoff and status as served
    after = _raw(rows["mis"])
    assert _but_ext(after) == _but_ext(before)                             # refused: every other column untouched
    import json                                                            # 297 C(ii): the key's third value only
    assert json.loads(after["external_ids"]) == {AF: "sbt-rbi-SBTB-2", "provider_orientation": "mismatch"}
    same = _raw(rows["same"])
    assert (same["home_score"], same["away_score"]) == (24, 17)
    assert [x["match_id"] for x in r["orientation_reversed"]] == [rows["rev"]]
    assert r["teams_mismatch_refused"] == [rows["mis"]]
    assert [x["match_id"] for x in r["refused"]] == [rows["mis"]]
    sc = {x["match_id"]: x for x in r["score_changed"]}
    assert sc[rows["rev"]]["provider_score"] == [31, 13]                   # the receipt prints it by team too
    assert r["updated"] == 2 and r["asked"] == 3
    lines = "\n".join(rbi.format_lines(r))
    assert "orientation reversed 1" in lines and "teams mismatch refused 1" in lines
    assert f"orientation REVERSED (scores written by team): match {rows['rev']}" in lines


# ---------------------------------------------------------------------------- intl-history (it calls _upsert_match)


def test_intl_history_receipt_lists_a_reversed_row_and_writes_its_scores_by_team(tmp_path):
    """intl_history.ingest goes through _upsert_match, so a re-listed fixture with home/away reversed is written by
    team; its receipt (and the intl-sync console) carries the two counts with the ids (item 3(c))."""
    import json
    from datetime import date
    import cli
    from src.ingestion import intl_history as ih
    from tests.test_intl_history import GROUNDS, fx, league

    def write(d, home, away, hg, ag):
        d.mkdir()
        json.dump({"response": [league(5, "UEFA Nations League", 2073)]}, open(d / "leagues.json", "w"))
        json.dump({"response": [fx(9907301, home, away, hg, ag, "Probe City", when="2073-06-07T18:45:00+00:00",
                                   league_season=2073)]}, open(d / "fixtures_5_2073.json", "w"))
        json.dump({"response": GROUNDS}, open(d / "teams_5_2073.json", "w"))
    init_db()
    write(tmp_path / "first", 880001, 880002, 2, 1)
    write(tmp_path / "again", 880002, 880001, 1, 2)                   # the same game, the pair served reversed
    r = ih.ingest(ih.Source(from_dir=str(tmp_path / "first")), date(2018, 1, 1))
    assert r["orientation_reversed"] == [] and r["teams_mismatch_refused"] == []
    with session_scope() as s:
        mid = s.execute(select(Match.id).where(Match.external_ids["api_football"].as_string() == "9907301")).scalar_one()
    out = CliRunner().invoke(cli.cli, ["intl-sync", "--from-dir", str(tmp_path / "again"), "--since", "2018-01-01"])
    assert out.exit_code == 0, out.output
    assert f"  orientation_reversed 1: {mid} · teams_mismatch_refused 0" in out.output.splitlines(), out.output
    row = _raw(mid)
    assert (row["home_score"], row["away_score"]) == (2, 1)                # by team: the stored home (880001) 2


# ---------------------------------------------------------------------------- the placeholder fill (addendum 500)
# ARCHITECT 2026-11-24, addendum 500 Q1, verbatim: "YES, A FILL IS A RULED CARVE-OUT, in your words of (b) and no wider:
# position by position, every side that differs is the stored placeholder, the other side is equal, each filled team is
# stored, is not the placeholder and is not the row's other team. A flip stays refused (292 item 3(d)); another game
# stays refused (3(a)). The fill is never silent: its own receipt line with the match ids." Q2: the placeholder is the
# provider's team id 345, never a name. Q3: the same pass. Q4: the upsert alone. Q5: PLACEHOLDER_RESOLVE_H and TWIN_H.
# ARCHITECT 2026-11-25, addendum 527 item 2: answer 1 "A HALF-FILL IS A FILL: RULE IT IN"; answer 2 "THE COLLEGE
# COMPETITION ONLY, for now: the narrower one line" (the college set the re-key holds,
# service.PLACEHOLDER_REKEY_COMPETITIONS, {"NCAA"}); answer 3 "REFUSE ON THE SWAPPED PAIR TOO, as the re-key does".
# The rows sit in test competition codes, one per test, outside "NCAA": the fill section adds one "NCAA" row, the scope
# test's. A test that reads the fill's own rules names its code to the `college` fixture, which stands the code in for
# the college competition (PLACEHOLDER_REKEY_COMPETITIONS, monkeypatched for that test only: the fill's scope and the
# re-key's placeholder window, as in "NCAA"). The scope itself is read unpatched, in the real "NCAA" and in another
# competition of the same source (test_the_fill_runs_in_the_college_competition_only).

PH_KICK = datetime(2026, 12, 5, 4, 0)       # the placeholder kickoff of eight of the nine rows (500 item 1(b))
PH_SERVED = PH_KICK + timedelta(hours=15)   # a served kickoff within PLACEHOLDER_RESOLVE_H of it


def _placeholder():
    """ONE Sport.NFL team carrying the provider's TBD team id (addendum 500 Q2), got or created: (our id, its id). Its
    NAME is deliberately not "TBD": Q2's "never matched by name" (a name match would fill nothing here; the TBD-named
    team without the id is test_a_team_named_like_the_placeholder_without_its_id_is_never_filled)."""
    init_db()
    with session_scope() as s:
        for t in s.execute(select(Team).where(Team.sport == Sport.NFL)).scalars():
            if (t.external_ids or {}).get(AF) == PLACEHOLDER_TEAM_ID:
                return t.id, PLACEHOLDER_TEAM_ID
        t = Team(sport=Sport.NFL, name="SBT placeholder by id", external_ids={AF: PLACEHOLDER_TEAM_ID})
        s.add(t)
        s.flush()
        return t.id, PLACEHOLDER_TEAM_ID


def _teams_of(mid):
    with session_scope() as s:
        m = s.get(Match, mid)
        return m.home_team_id, m.away_team_id


def _assert_refused_as_today(mid, before, res):
    """The unchanged MISMATCH path (292 item 3(a); 297 C(ii)): every column but the key untouched, the key `mismatch`,
    listed in teams_mismatch_refused, nothing filled."""
    import json
    after = _raw(mid)
    assert _but_ext(after) == _but_ext(before)
    assert json.loads(after["external_ids"]).get("provider_orientation") == "mismatch"
    assert res.teams_mismatch_refused == [mid] and res.placeholder_filled == [] and res.updated == 0


@pytest.fixture
def college(monkeypatch):
    """college(code): the test competition `code` stands in for the college competition, the fill's one scope (527
    item 2 answer 2): PLACEHOLDER_REKEY_COMPETITIONS plus `code`, for this test only (monkeypatch). Returns the code."""
    def stand_in(*codes):
        monkeypatch.setattr(svc, "PLACEHOLDER_REKEY_COMPETITIONS", svc.PLACEHOLDER_REKEY_COMPETITIONS | set(codes))
        return codes[0]
    return stand_in


def test_the_fill_verdict_is_position_by_position_and_no_wider():
    P, A, B, X, Y = 1, 2, 3, 4, 5
    assert placeholder_fill((P, P), (X, Y), P)                     # 33608's shape
    assert placeholder_fill((P, B), (X, B), P) and placeholder_fill((B, P), (B, X), P)
    assert not placeholder_fill((P, B), (B, X), P)                 # a flip stays refused (292 item 3(d))
    assert not placeholder_fill((P, B), (X, Y), P)                 # another game stays refused (292 item 3(a))
    assert not placeholder_fill((P, B), (P, X), P)                 # the differing side is a real team
    assert not placeholder_fill((A, B), (X, B), P)                 # no stored side is the placeholder
    assert not placeholder_fill((P, B), (B, B), P)                 # the filled team is the row's other team
    assert not placeholder_fill((P, P), (X, X), P)
    assert not placeholder_fill((P, P), (X, P), None)
    assert not placeholder_fill((P, B), (B, P), P)                 # REVERSED keeps its own path
    assert not placeholder_fill((P, B), (P, B), P)                 # SAME keeps its own path
    assert not placeholder_fill((P, B), (X, B), None)
    assert not placeholder_fill((P, B), (None, B), P) and not placeholder_fill((None, B), (X, B), P)
    # 527 item 2 answer 1, verbatim: "A HALF-FILL IS A FILL: RULE IT IN. (P,P) listed as (X,P) meets Q1's words side by
    # side": (P,P) listed (X,P) or (P,X) fills, the kept side the placeholder still; then (X,P) listed (X,Y) fills too
    assert placeholder_fill((P, P), (X, P), P) and placeholder_fill((P, P), (P, X), P)
    assert placeholder_fill((X, P), (X, Y), P) and placeholder_fill((P, X), (Y, X), P)
    assert not placeholder_fill((X, P), (P, X), P)                 # REVERSED keeps its own path
    assert not placeholder_fill((X, P), (Y, P), P)                 # the differing side is a real team


def test_the_placeholder_team_is_its_provider_id_never_a_name():
    """Q2, verbatim: "ONE ID, 345, held as data in placeholder.py beside the kickoff's definition, never matched by
    name"."""
    assert PLACEHOLDER_TEAM_ID == "345"
    assert is_placeholder_team("345") and is_placeholder_team(345)
    assert not is_placeholder_team(None) and not is_placeholder_team("TBD") and not is_placeholder_team("3450")


def test_a_row_with_the_placeholder_on_both_sides_takes_the_listed_pair_on_the_same_pass(college):
    """33608's shape (addendum 493 item 2(c), 500 item 1(b)): stored (P,P) at 19:00Z carrying the mismatch key; the
    listing names two teams. Q3: the pair then reads SAME and the unchanged SAME path writes scores, status and
    kickoff, and removes the key."""
    college("PHF2")
    p, _ = _placeholder()
    (x, xp), (y, yp) = _teams(Sport.NFL, AF)
    when = datetime(2026, 12, 5, 19, 0)
    mid = _stored("PHF2", Sport.NFL, AF, "phf-2", p, p, when=when,
                  ext={AF: "phf-2", "provider_orientation": "mismatch"})
    res = _sync("PHF2", AF, [_nm("PHF2", Sport.NFL, AF, "phf-2", xp, yp, when=when + timedelta(minutes=30),
                                 home_score=24, away_score=17, full_time_result=Result.HOME)])
    with session_scope() as s:
        m = s.get(Match, mid)
        assert (m.home_team_id, m.away_team_id) == (x, y)
        assert (m.home_score, m.away_score, m.full_time_result) == (24, 17, Result.HOME)
        assert m.status == MatchStatus.FINISHED and m.utc_date == when + timedelta(minutes=30) and m.status_raw == "FT"
        assert m.external_ids == {AF: "phf-2"}                       # the key removed (SAME)
    assert res.placeholder_filled == [mid] and res.teams_mismatch_refused == [] and res.orientation_reversed == []
    assert res.updated == 1 and res.skipped == 0 and res.created == 0


def test_a_row_with_the_placeholder_on_one_side_takes_the_listed_team_the_other_side_kept(college):
    college("PHF3")
    p, _ = _placeholder()
    (b, bp), (x, xp) = _teams(Sport.NFL, AF)
    mid = _stored("PHF3", Sport.NFL, AF, "phf-3", p, b, when=PH_KICK)
    res = _sync("PHF3", AF, [_nm("PHF3", Sport.NFL, AF, "phf-3", xp, bp, when=PH_KICK + timedelta(hours=15),
                                 status=MatchStatus.SCHEDULED)])
    with session_scope() as s:
        m = s.get(Match, mid)
        assert (m.home_team_id, m.away_team_id) == (x, b)
        assert m.utc_date == PH_KICK + timedelta(hours=15) and m.status == MatchStatus.SCHEDULED
    assert res.placeholder_filled == [mid] and res.teams_mismatch_refused == [] and res.updated == 1


@pytest.mark.parametrize("code,keep", [("PHF3H", "away"), ("PHF3A", "home")])
def test_a_half_fill_of_a_both_sides_placeholder_row_is_a_fill(college, code, keep):
    """527 item 2 answer 1, verbatim: "A HALF-FILL IS A FILL: RULE IT IN. (P,P) listed as (X,P) meets Q1's words side by
    side, and a bracket names its teams one at a time. The row then reads as the provider's does.": (P,P) listed (X,P)
    (or (P,X)) takes X on the same pass, the other side the placeholder still, the pair then SAME (the key removed);
    a later listing naming the second team fills that side too."""
    college(code)
    p, pp = _placeholder()
    (x, xp), (y, yp) = _teams(Sport.NFL, AF)
    when = datetime(2026, 12, 5, 19, 0)
    mid = _stored(code, Sport.NFL, AF, f"{code}-pp", p, p, when=when,
                  ext={AF: f"{code}-pp", "provider_orientation": "mismatch"})
    first = (xp, pp) if keep == "away" else (pp, xp)
    res = _sync(code, AF, [_nm(code, Sport.NFL, AF, f"{code}-pp", *first, when=when, status=MatchStatus.SCHEDULED)])
    assert _teams_of(mid) == ((x, p) if keep == "away" else (p, x))
    assert res.placeholder_filled == [mid] and res.teams_mismatch_refused == [] and res.updated == 1
    with session_scope() as s:
        assert s.get(Match, mid).external_ids == {AF: f"{code}-pp"}   # the row reads as the provider's does (SAME)
    second = (xp, yp) if keep == "away" else (yp, xp)
    res2 = _sync(code, AF, [_nm(code, Sport.NFL, AF, f"{code}-pp", *second, when=when, status=MatchStatus.SCHEDULED)])
    assert _teams_of(mid) == ((x, y) if keep == "away" else (y, x))
    assert res2.placeholder_filled == [mid] and res2.teams_mismatch_refused == []


def test_a_flip_of_a_placeholder_row_stays_refused(college):
    """(P,B) listed (B,X): the away side differs and is B, not the placeholder (292 item 3(d))."""
    college("PHF4")
    p, _ = _placeholder()
    (b, bp), (_x, xp) = _teams(Sport.NFL, AF)
    mid = _stored("PHF4", Sport.NFL, AF, "phf-4", p, b, when=PH_KICK)
    before = _raw(mid)
    res = _sync("PHF4", AF, [_nm("PHF4", Sport.NFL, AF, "phf-4", bp, xp, when=PH_KICK + timedelta(hours=15))])
    _assert_refused_as_today(mid, before, res)
    assert _teams_of(mid) == (p, b)


def test_another_game_on_a_placeholder_row_stays_refused(college):
    """(P,B) listed (X,Y): B differs and is not the placeholder (292 item 3(a))."""
    college("PHF5")
    p, _ = _placeholder()
    (b, _bp), (_x, xp), (_y, yp) = _teams(Sport.NFL, AF, 3)
    mid = _stored("PHF5", Sport.NFL, AF, "phf-5", p, b, when=PH_KICK)
    before = _raw(mid)
    res = _sync("PHF5", AF, [_nm("PHF5", Sport.NFL, AF, "phf-5", xp, yp, when=PH_KICK + timedelta(hours=15))])
    _assert_refused_as_today(mid, before, res)


def test_a_filled_team_not_stored_goes_the_unknown_team_path(college):
    """Q1: "each filled team is stored". A listed team never team-synced is the unknown-team refusal, as built."""
    import json
    college("PHF6")
    p, _ = _placeholder()
    (b, bp), = _teams(Sport.NFL, AF, 1)
    mid = _stored("PHF6", Sport.NFL, AF, "phf-6", p, b, when=PH_KICK)
    res = _sync("PHF6", AF, [_nm("PHF6", Sport.NFL, AF, "phf-6", "phf-never-synced", bp,
                                 when=PH_KICK + timedelta(hours=15))])
    assert res.skipped_ids == ["phf-6"] and res.teams_mismatch_refused == [mid] and res.placeholder_filled == []
    assert json.loads(_raw(mid)["external_ids"])["provider_orientation"] == "mismatch"
    assert _teams_of(mid) == (p, b)


def test_a_filled_team_that_is_the_rows_other_team_stays_refused(college):
    """Q1: each filled team "is not the row's other team": (P,B) listed (B,B), and (P,P) listed (X,X)."""
    college("PHF7")
    p, _ = _placeholder()
    (b, bp), (_x, xp) = _teams(Sport.NFL, AF)
    one = _stored("PHF7", Sport.NFL, AF, "phf-7a", p, b, when=PH_KICK)
    two = _stored("PHF7", Sport.NFL, AF, "phf-7b", p, p, when=PH_KICK + timedelta(days=4))
    res = _sync("PHF7", AF, [_nm("PHF7", Sport.NFL, AF, "phf-7a", bp, bp, when=PH_KICK + timedelta(hours=15)),
                             _nm("PHF7", Sport.NFL, AF, "phf-7b", xp, xp, when=PH_KICK + timedelta(days=4, hours=15))])
    assert res.teams_mismatch_refused == [one, two] and res.placeholder_filled == [] and res.updated == 0
    assert _teams_of(one) == (p, b) and _teams_of(two) == (p, p)


def test_a_served_kickoff_outside_the_placeholders_own_window_is_refused(college):
    """Q5: the kickoff window is PLACEHOLDER_RESOLVE_H (24h, inclusive as placeholder_resolved reads it): +25h is
    refused as a mismatch (the #902 class); +24h exactly is filled."""
    college("PHF8")
    p, _ = _placeholder()
    (b1, b1p), (_x1, x1p), (b2, b2p), (x2, x2p) = _teams(Sport.NFL, AF, 4)
    far = _stored("PHF8", Sport.NFL, AF, "phf-8a", p, b1, when=PH_KICK)
    edge = _stored("PHF8", Sport.NFL, AF, "phf-8b", p, b2, when=PH_KICK)
    before = _raw(far)
    res = _sync("PHF8", AF, [
        _nm("PHF8", Sport.NFL, AF, "phf-8a", x1p, b1p, when=PH_KICK + timedelta(hours=PLACEHOLDER_RESOLVE_H + 1)),
        _nm("PHF8", Sport.NFL, AF, "phf-8b", x2p, b2p, when=PH_KICK + timedelta(hours=PLACEHOLDER_RESOLVE_H))])
    after = _raw(far)
    assert _but_ext(after) == _but_ext(before)
    assert res.teams_mismatch_refused == [far] and res.placeholder_filled == [edge]
    assert _teams_of(edge) == (x2, b2)


@pytest.mark.parametrize("code,status,offset,filled,swapped", [
    ("PHF9A", MatchStatus.SCHEDULED, TWIN_H, False, False),
    ("PHF9E", MatchStatus.SCHEDULED, TWIN_H + 1, True, False),
    ("PHF9B", MatchStatus.CANCELLED, TWIN_H, True, False),
    ("PHF9D", MatchStatus.STALE_ORPHAN, TWIN_H, True, False),
    ("PHF9S", MatchStatus.SCHEDULED, TWIN_H, False, True),           # 527 item 2 answer 3: the swapped pair refuses
    ("PHF9T", MatchStatus.SCHEDULED, -TWIN_H, False, True),          # ... before the served kickoff too
    ("PHF9U", MatchStatus.SCHEDULED, TWIN_H + 1, True, True),
    ("PHF9V", MatchStatus.CANCELLED, TWIN_H, True, True)])
def test_a_live_row_holding_the_filled_pair_within_twin_h_refuses_the_fill(college, code, status, offset, filled,
                                                                           swapped):
    """Q5: the pair-collision window is the dry run's TWIN_H (48h), measured from the SERVED kickoff. A live stored
    (X,B) row of the season exactly TWIN_H after the served kickoff (15h + TWIN_H after the stored one) refuses the
    fill; one at TWIN_H + 1h does not; a CANCELLED or STALE_ORPHAN one at TWIN_H does not. 527 item 2 answer 3,
    verbatim: "REFUSE ON THE SWAPPED PAIR TOO, as the re-key does.": a live (B,X) row within TWIN_H, after or before the
    served kickoff, refuses it the same way; at TWIN_H + 1h, or CANCELLED, it does not."""
    college(code)
    p, _ = _placeholder()
    (b, bp), (x, xp) = _teams(Sport.NFL, AF)
    mid = _stored(code, Sport.NFL, AF, f"{code}-s", p, b, when=PH_KICK)
    hh, ha = (b, x) if swapped else (x, b)
    _stored(code, Sport.NFL, AF, f"{code}-held", hh, ha, when=PH_SERVED + timedelta(hours=offset), status=status)
    before = _raw(mid)
    res = _sync(code, AF, [_nm(code, Sport.NFL, AF, f"{code}-s", xp, bp, when=PH_SERVED)])
    if filled:
        assert res.placeholder_filled == [mid] and _teams_of(mid) == (x, b)
    else:
        _assert_refused_as_today(mid, before, res)


def test_a_row_of_another_season_holding_the_filled_pair_never_refuses_the_fill(college):
    """The collision is "a live row of the season" (plan (d)): a live (X,B) row stored under season 2025 at the served
    kickoff itself does not refuse the fill (the run's pair index is keyed by season)."""
    college("PHF9F")
    p, _ = _placeholder()
    (b, bp), (x, xp) = _teams(Sport.NFL, AF)
    mid = _stored("PHF9F", Sport.NFL, AF, "phf-9f", p, b, when=PH_KICK)
    other = _stored("PHF9F", Sport.NFL, AF, "phf-9f-2025", x, b, when=PH_SERVED)
    with session_scope() as s:
        s.get(Match, other).season = "2025"
    res = _sync("PHF9F", AF, [_nm("PHF9F", Sport.NFL, AF, "phf-9f", xp, bp, when=PH_SERVED)])
    assert res.placeholder_filled == [mid] and _teams_of(mid) == (x, b)


def test_a_row_created_earlier_in_the_listing_holding_the_filled_pair_refuses_the_fill(college):
    college("PHF9C")
    p, _ = _placeholder()
    (b, bp), (x, xp) = _teams(Sport.NFL, AF)
    mid = _stored("PHF9C", Sport.NFL, AF, "phf-9c", p, b, when=PH_KICK)
    before = _raw(mid)
    res = _sync("PHF9C", AF, [
        _nm("PHF9C", Sport.NFL, AF, "phf-9c-new", xp, bp, when=PH_KICK + timedelta(hours=15)),
        _nm("PHF9C", Sport.NFL, AF, "phf-9c", xp, bp, when=PH_KICK + timedelta(hours=15))])
    assert res.created == 1
    after = _raw(mid)
    assert _but_ext(after) == _but_ext(before)
    assert res.teams_mismatch_refused == [mid] and res.placeholder_filled == []


def test_a_filled_row_is_reindexed_so_a_later_listing_in_the_run_never_twins_it(college):
    """The run's pair index (__pairs__) moves the filled row to its new pair: a new id for (X,B) an hour on finds it and
    is refused by the re-key ("its id ... is still in this listing"), never created beside it."""
    college("PHF10")
    p, _ = _placeholder()
    (b, bp), (x, xp) = _teams(Sport.NFL, AF)
    mid = _stored("PHF10", Sport.NFL, AF, "phf-10", p, b, when=PH_KICK)
    res = _sync("PHF10", AF, [
        _nm("PHF10", Sport.NFL, AF, "phf-10", xp, bp, when=PH_KICK + timedelta(hours=15)),
        _nm("PHF10", Sport.NFL, AF, "phf-10-new", xp, bp, when=PH_KICK + timedelta(hours=16))])
    assert res.placeholder_filled == [mid] and res.rekey_refused == 1 and res.created == 0
    with session_scope() as s:
        c = s.execute(select(Competition).where(Competition.code == "PHF10")).scalar_one()
        assert s.execute(select(Match.id).where(Match.competition_id == c.id)).scalars().all() == [mid]


def test_a_filled_row_leaves_its_old_pair_so_a_new_id_for_that_pair_is_created_not_refused(college):
    """The run's pair index drops the filled row from its old (P,B) key: a later listing in the run with a new id for
    (P,B), within REKEY_WINDOW_H of the filled row's new kickoff, finds no row under (P,B) and is created as today (a
    stale entry would find the filled row and refuse it as "still in this listing")."""
    college("PHF11")
    p, pp = _placeholder()
    (b, bp), (x, xp) = _teams(Sport.NFL, AF)
    mid = _stored("PHF11", Sport.NFL, AF, "phf-11", p, b, when=PH_KICK)
    res = _sync("PHF11", AF, [
        _nm("PHF11", Sport.NFL, AF, "phf-11", xp, bp, when=PH_SERVED),
        _nm("PHF11", Sport.NFL, AF, "phf-11-new", pp, bp, when=PH_SERVED + timedelta(hours=5),
            status=MatchStatus.SCHEDULED)])
    assert res.placeholder_filled == [mid] and res.rekey_refused == 0 and res.created == 1
    assert _teams_of(mid) == (x, b)


def test_a_filled_row_holds_what_a_fresh_create_would_but_its_id(college):
    """Q3, verbatim: "The test shows the row then holds what a fresh create would, but its id." The reference row is
    the listing created into an empty competition, read and deleted (throwaway DB); then the same id is stored as a
    (P,P) placeholder row by the create path and the listing synced over it."""
    from dataclasses import replace
    college("PHFR")
    p, pp = _placeholder()
    (x, xp), (y, yp) = _teams(Sport.NFL, AF)
    with session_scope() as s:
        _comp(s, "PHFR", Sport.NFL)
    nm_xy = replace(_nm("PHFR", Sport.NFL, AF, "phf-r", xp, yp, when=PH_KICK + timedelta(hours=15),
                        home_score=31, away_score=28, full_time_result=Result.HOME), matchday=14, stage="FCS")
    nm_pp = replace(_nm("PHFR", Sport.NFL, AF, "phf-r", pp, pp, when=PH_KICK, status=MatchStatus.SCHEDULED),
                    matchday=14, stage="FCS")
    assert _sync("PHFR", AF, [nm_xy]).created == 1
    with session_scope() as s:
        c = s.execute(select(Competition).where(Competition.code == "PHFR")).scalar_one()
        ref = s.execute(select(Match.id).where(Match.competition_id == c.id)).scalar_one()
    want = _raw(ref)
    with session_scope() as s:
        s.delete(s.get(Match, ref))
    assert _sync("PHFR", AF, [nm_pp]).created == 1
    with session_scope() as s:
        mid = s.execute(select(Match.id).where(Match.competition_id == c.id)).scalar_one()
    assert _teams_of(mid) == (p, p)
    res = _sync("PHFR", AF, [nm_xy])
    assert res.placeholder_filled == [mid] and res.updated == 1
    got = _raw(mid)
    assert {k: v for k, v in got.items() if k != "id"} == {k: v for k, v in want.items() if k != "id"}


def test_refresh_by_id_is_not_touched_and_keeps_refusing(college, _rbi_quiet):
    """Q4, verbatim: "THE UPSERT ALONE. refresh-by-id is not touched and keeps refusing until the sync fills." The
    by-id answer names a team the row does not hold: refused, the row's teams kept."""
    import json
    college("PHF12")
    p, _ = _placeholder()
    (b, bp), (_x, xp) = _teams(Sport.NFL, AF)
    day = datetime.combine(utc_now_naive().date() + timedelta(days=2), datetime.min.time()) + timedelta(hours=4)
    mid = _stored("PHF12", Sport.NFL, AF, "phf-12", p, b, when=day)
    r = rbi.refresh("PHF12", Listing(AF, by_id={"phf-12": _nm("PHF12", Sport.NFL, AF, "phf-12", xp, bp,
                                                              when=day + timedelta(hours=15))}), days=7)
    assert r["teams_mismatch_refused"] == [mid]
    assert _teams_of(mid) == (p, b)
    assert json.loads(_raw(mid)["external_ids"])["provider_orientation"] == "mismatch"


def test_the_fill_runs_in_the_college_competition_only(college):
    """527 item 2 answer 2, verbatim: "THE COLLEGE COMPETITION ONLY, for now: the narrower one line.": the scope is
    {"NCAA"}, read unpatched here. The same (P,B) row listed (X,B) fills in "NCAA", and in another competition of the
    same source (api_american_football, an NFL-sport code outside the scope) is refused as main refuses it. The source
    condition stays on its own: another source's team carrying "345" is no placeholder, its row refused as today even
    with its code stood in for the college competition."""
    assert svc.PLACEHOLDER_REKEY_COMPETITIONS == frozenset({"NCAA"})
    p, _ = _placeholder()
    (b, bp), (x, xp), (b2, b2p), (_x2, x2p) = _teams(Sport.NFL, AF, 4)
    mid = _stored("NCAA", Sport.NFL, AF, "phf-ncaa", p, b, when=PH_KICK)
    res = _sync("NCAA", AF, [_nm("NCAA", Sport.NFL, AF, "phf-ncaa", xp, bp, when=PH_SERVED,
                                 status=MatchStatus.SCHEDULED)])
    assert res.placeholder_filled == [mid] and res.teams_mismatch_refused == [] and _teams_of(mid) == (x, b)
    assert "PHFX" not in svc.PLACEHOLDER_REKEY_COMPETITIONS
    other = _stored("PHFX", Sport.NFL, AF, "phf-x", p, b2, when=PH_KICK)
    before = _raw(other)
    ores = _sync("PHFX", AF, [_nm("PHFX", Sport.NFL, AF, "phf-x", x2p, b2p, when=PH_SERVED)])
    _assert_refused_as_today(other, before, ores)
    assert _teams_of(other) == (p, b2)
    college("PHFS")
    init_db()
    with session_scope() as s:
        soc = Team(sport=Sport.SOCCER, name="SBT soccer 345", external_ids={SOC: PLACEHOLDER_TEAM_ID})
        s.add(soc)
        s.flush()
        sp = soc.id
    (sb, sbp), (_sx, sxp) = _teams(Sport.SOCCER, SOC)
    smid = _stored("PHFS", Sport.SOCCER, SOC, "phf-s", sp, sb, when=PH_KICK)
    before = _raw(smid)
    sres = _sync("PHFS", SOC, [_nm("PHFS", Sport.SOCCER, SOC, "phf-s", sxp, sbp, when=PH_SERVED)])
    _assert_refused_as_today(smid, before, sres)


def test_a_team_named_like_the_placeholder_without_its_id_is_never_filled(college):
    """Q2: "never matched by name". A stored team named "TBD" whose provider id is not 345 is a team like any other:
    its row listed with another team there is refused as today (its code stood in for the college competition, so the
    refusal is the name's, not the scope's)."""
    college("PHF13")
    init_db()
    with session_scope() as s:
        tbd = Team(sport=Sport.NFL, name="TBD", external_ids={AF: f"sbt-tbd-{utc_now_naive():%H%M%S%f}"})
        s.add(tbd)
        s.flush()
        n = tbd.id
    (b, bp), (_x, xp) = _teams(Sport.NFL, AF)
    mid = _stored("PHF13", Sport.NFL, AF, "phf-13", n, b, when=PH_KICK)
    before = _raw(mid)
    res = _sync("PHF13", AF, [_nm("PHF13", Sport.NFL, AF, "phf-13", xp, bp, when=PH_SERVED)])
    _assert_refused_as_today(mid, before, res)


def test_the_cli_receipt_prints_the_fill_on_its_own_line_with_the_ids(college, monkeypatch):
    """Q1: "its own receipt line with the match ids", before the scores-by-team line; none when nothing is filled."""
    import cli
    college("PHF14")
    p, _ = _placeholder()
    (b, bp), (x, xp) = _teams(Sport.NFL, AF)
    mid = _stored("PHF14", Sport.NFL, AF, "phf-14", p, b, when=PH_KICK)
    fake = Listing(AF, [_nm("PHF14", Sport.NFL, AF, "phf-14", xp, bp, when=PH_KICK + timedelta(hours=15))])
    monkeypatch.setattr(cli, "_adapter_for_competition", lambda c: fake)
    monkeypatch.setattr(cli, "_mlb_fallback", lambda c: False)
    res = CliRunner().invoke(cli.cli, ["sync-matches", "--competition", "PHF14", "--season", "2026"])
    assert res.exit_code == 0, res.output
    lines = res.output.splitlines()
    sbt = "orientation_reversed 0 · teams_mismatch_refused 0"
    assert f"placeholder_filled 1: {mid}" in lines and sbt in lines, res.output
    assert lines.index(f"placeholder_filled 1: {mid}") < lines.index(sbt)
    assert _teams_of(mid) == (x, b)
    again = CliRunner().invoke(cli.cli, ["sync-matches", "--competition", "PHF14", "--season", "2026"])
    assert again.exit_code == 0 and "placeholder_filled" not in again.output, again.output


def test_the_admin_sync_job_carries_the_fill(college, monkeypatch):
    from src.web.routes import admin
    college("PHF14A")
    p, _ = _placeholder()
    (b, bp), (x, xp) = _teams(Sport.NFL, AF)
    mid = _stored("PHF14A", Sport.NFL, AF, "phf-14a", p, b, when=PH_KICK)
    fake = Listing(AF, [_nm("PHF14A", Sport.NFL, AF, "phf-14a", xp, bp, when=PH_KICK + timedelta(hours=15))])
    monkeypatch.setattr(admin, "_adapter_for_competition", lambda c: fake)
    out = admin._job_sync_matches(competition_code="PHF14A", season="2026", seasons=0)
    assert out.endswith(f"orientation_reversed 0 · teams_mismatch_refused 0 · placeholder_filled 1: {mid}"), out


def test_the_admin_multi_season_job_logs_the_fill_in_its_seasons_block(college, monkeypatch):
    """Q1 "never silent": a --seasons job's own season block carries the fill's line, beside the collision line."""
    from src.web.routes import admin

    class _Log:
        def __init__(self):
            self.lines = []

        def append_log(self, s):
            self.lines.append(s)

    college("PHF14B")
    p, _ = _placeholder()
    (b, bp), (x, xp) = _teams(Sport.NFL, AF)
    mid = _stored("PHF14B", Sport.NFL, AF, "phf-14b", p, b, when=PH_KICK)
    fake = Listing(AF, [_nm("PHF14B", Sport.NFL, AF, "phf-14b", xp, bp, when=PH_SERVED)])
    monkeypatch.setattr(admin, "_adapter_for_competition", lambda c: fake)
    job = _Log()
    out = admin._job_sync_matches(competition_code="PHF14B", season=None, seasons=1, job=job)
    assert f"  placeholder_filled 1: {mid}" in job.lines, job.lines
    assert out.endswith(f"placeholder_filled 1: {mid}"), out
