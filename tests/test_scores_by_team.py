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
from src.ingestion.score_orientation import MISMATCH, REVERSED, SAME, orientation, scores_by_team
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


def test_a_mismatched_pair_is_refused_the_row_byte_identical_and_counted():
    (h, _hp), (a, ap), (_x, xp) = _teams(Sport.NFL, AF, 3)
    mid = _stored("SBTN", Sport.NFL, AF, "sbt-mis-1", h, a, home_score=10, away_score=3,
                  full_time_result=Result.HOME, status=MatchStatus.FINISHED)
    before = _raw(mid)
    res = _sync("SBTN", AF, [_nm("SBTN", Sport.NFL, AF, "sbt-mis-1", xp, ap, when=KICK + timedelta(hours=2),
                                 home_score=0, away_score=44, full_time_result=Result.AWAY)])
    assert _raw(mid) == before                                           # every column, untouched
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
            f"reverse; the row untouched): match {mis}") in lines, res.output


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
    """The NCAA placeholder (04:00Z, src/ingestion/placeholder.py) is a KICKOFF, never a team: its teams are real and
    its re-key window takes the same pair only, so the helper reads SAME and nothing changes."""
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
    assert _raw(rows["mis"]) == before                                     # refused: every column untouched
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
