"""NCAA CFBD SCOPE + JOIN (ARCHITECT 2026-10-08, addendum 10 item 3). Pins, on synthetic fixtures only:
- J1: a first-pass-unmatched source game is retried within ±36h by the same name tiers; it joins (join_via
  'dateshift', listed with both kickoffs and the offset) only on exactly one (match, orientation), a match not
  already joined, and agreeing scores; a name fit whose scores disagree stays unmatched, listed with both scores;
- J2: our names html-unescaped before normalization in the join and alias vetting; ids whose unescaped names are
  identical are one team (lowest id) in the v1r stream, every group and changed name listed; no DB rewrite;
- J3: the four pinned aliases each resolve to exactly one of our teams;
- J4: season_type (nullable, its own idempotent migration) filled from CFBD's seasonType as served, carried on Game;
- SCOPE: the v1r stream is the CFBD-labelled games only; coverage = labelled / CFBD's completed both-FBS games
  (before/after on a synthetic fixture), every unlabelled game listed."""
import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import inspect, select, text

from src.db.schema import Competition, Match, MatchStatus, NCAACFBDLabel, Sport, Team
from src.ingestion import ncaa_cfbd as nc
from src.ingestion.match_lookup import normalize_team_name
from src.walters import ncaa_backtest as nb


def rec(gid, home, away, hp, ap, start, neutral=False, hc="fbs", ac="fbs", season_type="regular", **kw):
    return {"id": gid, "season": 2084, "seasonType": season_type, "startDate": start, "completed": True,
            "neutralSite": neutral, "homeTeam": home, "homeClassification": hc, "homePoints": hp,
            "awayTeam": away, "awayClassification": ac, "awayPoints": ap, **kw}


KEYS = nc.discover(rec(1, "a", "b", 1, 0, "2084-09-01T00:00:00Z"))[0]


def ours(mid, teams, h, a, at, hs, as_, season="2084"):
    return nc.Ours(mid, at, season, h, a, nc.our_norm(teams[h]), nc.our_norm(teams[a]), hs, as_)


def build(records, our_list, teams, aliases=None):
    our_list = sorted(our_list, key=lambda m: (m.utc_date, m.id))
    return nc.build_labels(records, KEYS, our_list, teams, aliases or {}, 2084, "fbs")


# --- J1: the dateshift retry ------------------------------------------------------------------------------------

T = {1: "Shift A", 2: "Shift B", 3: "Shift C", 4: "Shift D", 5: "Shift E", 6: "Shift F", 7: "Shift G",
     8: "Shift H", 9: "Shift I", 10: "Shift J"}


def test_dateshift_joins_one_day_early_kickoff_with_both_kickoffs_and_offset():
    # our row stored one day early (the 00:00-03:59 UTC finding): first pass (±12h) misses it, the retry joins
    o = [ours(101, T, 1, 2, datetime(2084, 9, 5, 1, 30), 27, 13)]
    r = build([rec(9001, "Shift A", "Shift B", 27, 13, "2084-09-06T01:30:00.000Z")], o, T)
    assert r.counts["joined"] == 1 and r.counts["join_via_dateshift"] == 1 and r.counts["unmatched"] == 0
    row = r.rows[0]
    assert (row["match_id"], row["join_via"], row["orientation"], row["home_score"]) == (101, "dateshift", "same", 27)
    assert len(r.dateshift) == 1
    line = r.dateshift[0]
    assert "CFBD kickoff 2084-09-06 01:30" in line and "ours 2084-09-05 01:30" in line and "offset -24.0h" in line
    text_ = "\n".join(nc.receipt_lines(r))
    assert "DATESHIFT rows (J1" in text_ and "offset -24.0h" in text_ and "dateshift 1" in text_


def test_dateshift_swapped_orientation_scores_compared_in_that_orientation():
    o = [ours(102, T, 2, 1, datetime(2084, 9, 12, 2), 13, 27)]            # ours: B home 13, A away 27
    r = build([rec(9002, "Shift A", "Shift B", 27, 13, "2084-09-13T02:00:00.000Z")], o, T)
    assert r.rows[0]["orientation"] == "swapped" and (r.rows[0]["home_score"], r.rows[0]["away_score"]) == (13, 27)
    assert r.rows[0]["join_via"] == "dateshift"


def test_dateshift_name_fit_with_disagreeing_scores_stays_unmatched_listed_with_both_scores():
    o = [ours(103, T, 3, 4, datetime(2084, 9, 5, 2), 20, 10)]
    r = build([rec(9003, "Shift C", "Shift D", 21, 10, "2084-09-06T02:00:00.000Z")], o, T)
    assert r.rows == [] and r.counts["unmatched"] == 1 and r.counts["dateshift_score_disagree"] == 1
    assert "scores disagree: ours 20-10, CFBD in our orientation 21-10; stays unmatched" in r.unmatched[0]
    assert "our match 103" in r.unmatched[0] and "offset -24.0h" in r.unmatched[0]
    assert any("scores disagree" in x for x in r.unlabelled)
    # our row unscored: the scores cannot agree -> unmatched, ours shown as "—"
    o = [ours(104, T, 3, 4, datetime(2084, 9, 5, 2), None, None)]
    r = build([rec(9004, "Shift C", "Shift D", 21, 10, "2084-09-06T02:00:00.000Z")], o, T)
    assert r.rows == [] and "ours —, CFBD in our orientation 21-10" in r.unmatched[0]


def test_dateshift_refuses_a_match_the_first_pass_already_joined():
    o = [ours(105, T, 5, 6, datetime(2084, 9, 6, 19), 30, 3)]
    recs = [rec(9005, "Shift E", "Shift F", 30, 3, "2084-09-06T19:00:00.000Z"),     # first pass joins 105
            rec(9006, "Shift E", "Shift F", 30, 3, "2084-09-08T01:00:00.000Z")]     # +30h: only 105 fits
    r = build(recs, o, T)
    assert [x["source_game_id"] for x in r.rows] == [9005] and r.rows[0]["join_via"] == "exact"
    assert r.counts["dateshift_already_joined"] == 1 and r.counts["unmatched"] == 1
    assert "that match is already joined; stays unmatched" in r.unmatched[0] and "our match 105" in r.unmatched[0]


def test_dateshift_needs_exactly_one_fit_and_stays_inside_36h():
    o = [ours(106, T, 7, 8, datetime(2084, 9, 5, 2), 14, 7), ours(107, T, 7, 8, datetime(2084, 9, 7, 2), 14, 7)]
    r = build([rec(9007, "Shift G", "Shift H", 14, 7, "2084-09-06T02:00:00.000Z")], o, T)
    assert r.rows == [] and r.counts["dateshift_ambiguous"] == 1
    assert "dateshift: 2 (match, orientation) fits" in r.unmatched[0]
    o = [ours(108, T, 9, 10, datetime(2084, 9, 4, 13), 14, 7)]               # 37h early: outside the window
    r = build([rec(9008, "Shift I", "Shift J", 14, 7, "2084-09-06T02:00:00.000Z")], o, T)
    assert r.rows == [] and r.counts["unmatched"] == 1 and r.counts["dateshift_ambiguous"] == 0
    assert r.unmatched == ["2084-09-06 Shift J @ Shift I"]                   # no fit: listed plainly


def test_two_dateshift_rows_on_one_match_are_both_refused():
    o = [ours(109, T, 1, 3, datetime(2084, 10, 1, 2), 10, 7)]
    recs = [rec(9009, "Shift A", "Shift C", 10, 7, "2084-10-02T02:00:00.000Z"),
            rec(9010, "Shift A", "Shift C", 10, 7, "2084-09-30T02:00:00.000Z")]
    r = build(recs, o, T)
    assert r.rows == [] and r.counts["duplicate_target_refused"] == 2


def test_first_pass_join_is_never_reclassified_as_dateshift():
    o = [ours(110, T, 2, 4, datetime(2084, 10, 3, 19), 10, 7)]
    r = build([rec(9011, "Shift B", "Shift D", 10, 7, "2084-10-03T23:00:00.000Z")], o, T)
    assert r.rows[0]["join_via"] == "exact" and r.dateshift == []


# --- J2: html-unescaped names; the id merge -----------------------------------------------------------------

def test_escaped_our_name_joins_after_unescape_and_is_listed():
    teams = {201: "Hawai&#x27;i", 202: "Esc Opp"}
    o = [ours(301, teams, 201, 202, datetime(2084, 9, 6, 23), 24, 17)]
    # before J2 (the plain normalize): our 'hawai&#x27;i' never equals CFBD's 'hawaii'
    assert normalize_team_name("Hawai&#x27;i") != normalize_team_name("Hawai'i")
    assert nc.our_norm("Hawai&#x27;i") == normalize_team_name("Hawai'i") == "hawaii"
    r = build([rec(9101, "Hawai'i", "Esc Opp", 24, 17, "2084-09-06T23:00:00.000Z")], o, teams)
    assert r.counts["joined"] == 1 and r.rows[0]["join_via"] == "exact"
    assert r.escaped == [(201, "Hawai&#x27;i", "Hawai'i")]
    assert "team 201: 'Hawai&#x27;i' -> \"Hawai'i\"" in "\n".join(nc.receipt_lines(r))


def test_alias_vetting_unescapes_our_names():
    ok, refused = nc.vet_aliases({"Hawaii Rainbow Warriors": "Hawai'i"}, {201: "Hawai&#x27;i", 202: "Esc Opp"})
    assert ok == {"Hawaii Rainbow Warriors": "Hawai'i"} and refused == []
    # both stored rows unescape to the same name: in alias vetting that is two targets (the merge is the stream's)
    ok, refused = nc.vet_aliases({"Hawaii Rainbow Warriors": "Hawai'i"}, {201: "Hawai&#x27;i", 203: "Hawai'i"})
    assert ok == {} and refused[0][2].startswith("target names 2 of our NCAA teams")


def test_team_merge_lowest_id_every_group_and_changed_name_listed():
    teams = {7: "Hawai'i", 3: "Hawai&#x27;i", 9: "Texas A&amp;M", 4: "Texas A&M", 5: "Solo U", 6: "Hawaii"}
    tm = nb.team_merge(teams)
    assert tm.canon == {3: 3, 7: 3, 4: 4, 9: 4} and tm(5) == 5 and tm(6) == 6     # 'Hawaii' != "Hawai'i"
    assert tm.groups == [[(3, "Hawai&#x27;i"), (7, "Hawai'i")], [(4, "Texas A&M"), (9, "Texas A&amp;M")]]
    assert tm.changed == [(3, "Hawai&#x27;i", "Hawai'i"), (9, "Texas A&amp;M", "Texas A&M")]
    lines = "\n".join(tm.lines())
    assert "2 group(s) · 2 name(s) changed" in lines and "one team, keyed 3: 3 'Hawai&#x27;i' · 7 \"Hawai'i\"" in lines
    lab = dict(label_source="cfbd", orientation="same")
    games = [nb.Game(7, 5, "2025", datetime(2025, 9, 6), 21, 7, **lab),
             nb.Game(5, 3, "2025", datetime(2025, 9, 13), 14, 28, **lab),
             nb.Game(9, 6, "2026", datetime(2026, 9, 6), 30, 20, **lab)]
    v = nb.v1r_stream(games, teams)
    assert [(g.home_id, g.away_id) for g in v.stream.train] == [(3, 5), (5, 3)]     # one Hawai'i
    assert [(g.home_id, g.away_id) for g in v.stream.test] == [(4, 6)]
    assert "one team, keyed 4: 4 'Texas A&M' · 9 'Texas A&amp;M'" in "\n".join(v.lines())


def test_v1r_stream_merge_never_writes_teams(fresh_db):
    from src.db.database import init_db, session_scope

    init_db()
    with session_scope() as s:
        comp = Competition(sport=Sport.NFL, code="NCAA", name="NCAA", area="USA", type="LEAGUE")
        a, b, c = Team(sport=Sport.NFL, name="Hawai'i"), Team(sport=Sport.NFL, name="Hawai&#x27;i"), \
            Team(sport=Sport.NFL, name="Merge Opp")
        s.add_all([comp, a, b, c])
        s.flush()
        for i, (h, aw) in enumerate(((a, c), (c, b))):
            m = Match(sport=Sport.NFL, competition_id=comp.id, season="2025", utc_date=datetime(2025, 9, 6 + 7 * i),
                      status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=aw.id, home_score=21,
                      away_score=7, stage="FBS (Division I-A)")
            s.add(m)
            s.flush()
            s.add(NCAACFBDLabel(match_id=m.id, source="cfbd", source_game_id=500 + i, season="2025",
                                orientation="same", neutral=False, home_score=21, away_score=7,
                                fetched_at=datetime(2026, 10, 8)))
        ids = (a.id, b.id)
    with session_scope() as s:
        before = {t.id: t.name for t in s.execute(select(Team)).scalars()}
    v = nb.load_v1r_stream()
    assert {g.home_id for g in v.stream.train} | {g.away_id for g in v.stream.train} == {min(ids), c.id}
    assert v.merge.groups == [[(ids[0], "Hawai'i"), (ids[1], "Hawai&#x27;i")]]
    with session_scope() as s:
        assert {t.id: t.name for t in s.execute(select(Team)).scalars()} == before   # teams never rewritten


# --- J3: the pinned aliases ---------------------------------------------------------------------------------

OPERATOR_LISTING = {401: "Appalachian State", 402: "Apprentice School", 403: "Mass Maritime", 404: "UMASS Dartmouth",
                    405: "UMass", 406: "Buffalo State", 407: "Rice Owls", 408: "Minnesota"}


def test_j3_pins_each_resolve_to_exactly_one_of_our_teams():
    pinned = nc.load_aliases(nc.ALIAS_FILE)
    assert pinned == {"App State": "Appalachian State", "Massachusetts": "UMass", "Buffalo": "Buffalo State",
                      "Rice": "Rice Owls"}
    ok, refused = nc.vet_aliases(pinned, OPERATOR_LISTING)
    assert ok == pinned and refused == []
    by_norm = {}
    for tid, n in OPERATOR_LISTING.items():
        by_norm.setdefault(nc.our_norm(n), []).append(tid)
    assert {src: by_norm[nc.our_norm(tgt)] for src, tgt in pinned.items()} == {
        "App State": [401], "Massachusetts": [405], "Buffalo": [406], "Rice": [407]}


def test_j3_buffalo_at_minnesota_joins_swapped_via_alias():
    # the operator's case: CFBD Buffalo @ Minnesota; ours Minnesota 23 @ Buffalo State 10 (our home = Buffalo State)
    o = [ours(33619, OPERATOR_LISTING, 406, 408, datetime(2084, 9, 6, 0), 10, 23)]
    r = build([rec(9301, "Minnesota", "Buffalo", 23, 10, "2084-09-06T00:00:00.000Z")], o, OPERATOR_LISTING,
              nc.load_aliases(nc.ALIAS_FILE))
    row = r.rows[0]
    assert (row["match_id"], row["orientation"], row["join_via"]) == (33619, "swapped", "alias")
    assert (row["home_score"], row["away_score"]) == (10, 23) and row["correction_reason"] is None


# --- J4: season_type ------------------------------------------------------------------------------------------

@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import src.db.database as db

    eng = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=eng, autoflush=False, future=True,
                                                         expire_on_commit=False))
    return eng


def test_build_labels_fills_season_type_as_served():
    o = [ours(501, T, 1, 2, datetime(2084, 12, 20, 19), 30, 3), ours(502, T, 3, 4, datetime(2084, 9, 6, 19), 3, 0)]
    recs = [rec(9401, "Shift A", "Shift B", 30, 3, "2084-12-20T19:00:00.000Z", season_type="postseason"),
            rec(9402, "Shift C", "Shift D", 3, 0, "2084-09-06T19:00:00.000Z", season_type=None)]
    by = {x["match_id"]: x for x in build(recs, o, T).rows}
    assert by[501]["season_type"] == "postseason" and by[502]["season_type"] is None


def _old_schema(eng):
    """The side table as #333 shipped it: no season_type column."""
    from src.db.database import init_db

    import migrate_ncaa_cfbd_labels as mig
    init_db()
    assert mig.main() == 0
    with eng.begin() as conn:
        conn.execute(text("ALTER TABLE ncaa_cfbd_labels DROP COLUMN season_type"))
    assert "season_type" not in {c["name"] for c in inspect(eng).get_columns("ncaa_cfbd_labels")}


def _world(s):
    comp = Competition(sport=Sport.NFL, code="NCAA", name="NCAA", area="USA", type="LEAGUE")
    t = {n: Team(sport=Sport.NFL, name=n) for n in ("J4 A", "J4 B", "J4 C", "J4 D", "J4 FCS")}
    s.add_all([comp, *t.values()])
    s.flush()
    ms = {}
    for key, (h, a, at, hs, as_) in {
            "reg": ("J4 A", "J4 B", datetime(2084, 9, 6, 19), 31, 10),
            "post": ("J4 C", "J4 D", datetime(2084, 12, 20, 19), 28, 14),
            "fcs": ("J4 A", "J4 FCS", datetime(2084, 9, 13, 19), 56, 0)}.items():
        m = Match(sport=Sport.NFL, competition_id=comp.id, season="2084", utc_date=at, status=MatchStatus.FINISHED,
                  home_team_id=t[h].id, away_team_id=t[a].id, home_score=hs, away_score=as_,
                  stage="FBS (Division I-A)")
        s.add(m)
        s.flush()
        ms[key] = m.id
    return ms


J4_RECS = [rec(9501, "J4 A", "J4 B", 31, 10, "2084-09-06T19:00:00.000Z"),
           rec(9502, "J4 C", "J4 D", 28, 14, "2084-12-20T19:00:00.000Z", season_type="postseason"),
           rec(9503, "J4 A", "J4 FCS", 56, 0, "2084-09-13T19:00:00.000Z", ac="fcs"),       # not both-FBS
           rec(9504, "J4 B", "Nowhere Tech", 20, 0, "2084-09-20T19:00:00.000Z")]           # in scope, unmatched


def test_migration_adds_nullable_column_idempotently_and_ingest_fills_it(fresh_db, tmp_path, monkeypatch, capsys):
    import migrate_ncaa_cfbd_season_type as mig_st
    from src.db.database import session_scope

    _old_schema(fresh_db)
    with session_scope() as s:
        ms = _world(s)
    monkeypatch.setattr(nc, "ALIAS_FILE", tmp_path / "aliases.json")
    (tmp_path / "aliases.json").write_text(json.dumps({"aliases": {}}))
    f = tmp_path / "cfbd_games_2084.json"
    f.write_text(json.dumps(J4_RECS))
    # before the migration: readers still work (season_type never selected), the ingest refuses to write
    assert {g.match_id: g.season_type for g in nb.load_games()} == {ms["reg"]: None, ms["post"]: None,
                                                                     ms["fcs"]: None}
    with pytest.raises(nc.CFBDError, match="migrate_ncaa_cfbd_season_type.py"):
        nc.run([2084], from_file=str(f), out=lambda *_: None)
    assert nc.run([2084], from_file=str(f), dry_run=True, out=lambda *_: None) == 0
    capsys.readouterr()
    assert mig_st.main() == 0 and "+ Adding ncaa_cfbd_labels.season_type" in capsys.readouterr().out
    assert mig_st.main() == 0 and "already exists" in capsys.readouterr().out          # idempotent
    col = {c["name"]: c for c in inspect(fresh_db).get_columns("ncaa_cfbd_labels")}["season_type"]
    assert col["nullable"] is True
    lines = []
    assert nc.run([2084], from_file=str(f), out=lines.append) == 0
    with session_scope() as s:
        got = {r.match_id: r.season_type for r in s.execute(select(NCAACFBDLabel)).scalars()}
    assert got == {ms["reg"]: "regular", ms["post"]: "postseason"}
    by = {g.match_id: g for g in nb.load_games()}
    assert by[ms["post"]].season_type == "postseason" and by[ms["reg"]].season_type == "regular"
    assert by[ms["fcs"]].season_type is None and by[ms["fcs"]].label_source == "matches"


def test_migration_refuses_without_the_side_table(fresh_db, capsys):
    import migrate_ncaa_cfbd_season_type as mig_st
    from src.db.database import init_db

    init_db()
    with fresh_db.begin() as conn:
        conn.execute(text("DROP TABLE ncaa_cfbd_labels"))
    assert mig_st.main() == 1 and "migrate_ncaa_cfbd_labels.py` first" in capsys.readouterr().out


# --- SCOPE: the stream and the coverage denominator -------------------------------------------------------------

def test_v1r_stream_excludes_unlabelled_games():
    lab = dict(label_source="cfbd", orientation="same")
    games = [nb.Game(1, 2, "2025", datetime(2025, 9, 6), 21, 7, **lab),
             nb.Game(1, 3, "2025", datetime(2025, 9, 13), 70, 0),                   # FCS opponent: no label
             nb.Game(2, 3, "2026", datetime(2026, 9, 6), 14, 10, **lab),
             nb.Game(4, 5, "2026", datetime(2026, 9, 13), 3, 0)]
    v = nb.v1r_stream(games, {i: f"Team {i}" for i in range(1, 6)})
    assert [(g.home_id, g.away_id) for g in v.stream.train + v.stream.test] == [(1, 2), (2, 3)]
    assert dict(v.unlabelled) == {"2025": 1, "2026": 1} and dict(v.labelled) == {"2025": 1, "2026": 1}
    assert "NOT walked, NOT scored" in "\n".join(v.lines())
    full = nb.build_stream(games)                                     # #79's all-division stream is unchanged
    assert (len(full.train), len(full.test)) == (2, 2)


def test_coverage_denominator_before_and_after():
    """The 2026-10-07 build divided by every kept stream game (all divisions); SCOPE divides by CFBD's
    completed both-FBS games. Same fixture, both readings."""
    lab = dict(label_source="cfbd", orientation="same")
    labelled = [nb.Game(1000 + i, 2000 + i, "2025", datetime(2025, 9, 1) + timedelta(hours=i), 21, 7, **lab)
                for i in range(96)]
    fcs = [nb.Game(3000 + i, 4000 + i, "2025", datetime(2025, 9, 1) + timedelta(hours=i), 49, 3) for i in range(60)]
    stream = nb.build_stream(labelled + fcs)
    before = nb.label_coverage(stream)["2025"]
    assert (before["covered"], before["n"]) == (96, 156) and round(before["covered_share"], 4) == 0.6154
    assert before["covered_share"] < nc.COVERAGE_MIN                  # BEFORE: 61.5% -> the condition read NO
    after = nc.fbs_coverage(in_scope=100, labelled=96)                # CFBD: 100 completed both-FBS, 96 labelled
    assert after == {"in_scope": 100, "labelled": 96, "share": 0.96, "ok": True}   # AFTER: 96.0% -> YES
    assert nc.fbs_coverage(100, 94)["ok"] is False and nc.fbs_coverage(100, 95)["ok"] is True
    assert nc.fbs_coverage(0, 0) == {"in_scope": 0, "labelled": 0, "share": None, "ok": False}


def test_ingest_receipt_states_the_coverage_and_lists_every_unlabelled_game():
    o = [ours(601 + i, {**T, 99: "Shift Z"}, 1, 2, datetime(2084, 9, 1) + timedelta(days=7 * i), 7, 3)
         for i in range(19)]
    recs = [rec(9600 + i, "Shift A", "Shift B", 7, 3, f"{datetime(2084, 9, 1) + timedelta(days=7 * i):%Y-%m-%d}"
                f"T00:00:00.000Z") for i in range(19)]
    recs += [rec(9700, "Lost U", "Shift A", 3, 0, "2084-08-25T00:00:00.000Z"),
             rec(9701, "Shift A", "FCS U", 63, 0, "2084-08-26T00:00:00.000Z", ac="fcs")]   # out of scope
    r = build(recs, o, {**T, 99: "Shift Z"})
    assert (r.counts["completed_in_scope"], r.counts["joined"]) == (20, 19)
    text_ = "\n".join(nc.receipt_lines(r))
    assert "COVERAGE (SCOPE, ARCHITECT 2026-10-08): labelled 19 / CFBD completed both-FBS 20 = 95.0% · >= 95%: YES" \
        in text_
    assert "UNLABELLED in-scope games (1, every one" in text_ and "2084-08-25 Shift A @ Lost U — unmatched" in text_
    assert "FCS U" not in text_.split("UNLABELLED")[1]


def test_stored_coverage_reads_the_side_table_and_the_payload_it_names(fresh_db, tmp_path, monkeypatch):
    import migrate_ncaa_cfbd_labels as mig
    from src.db.database import init_db, session_scope

    init_db()
    assert mig.main() == 0
    with session_scope() as s:
        _world(s)
    monkeypatch.setattr(nc, "ALIAS_FILE", tmp_path / "aliases.json")
    (tmp_path / "aliases.json").write_text(json.dumps({"aliases": {}}))
    f = tmp_path / "cfbd_games_2084.json"
    f.write_text(json.dumps(J4_RECS))
    lines = []
    assert nc.run([2084], from_file=str(f), out=lines.append) == 0
    assert any("labelled 2 / CFBD completed both-FBS 3 = 66.7% · >= 95%: NO" in x for x in lines)
    with session_scope() as s:
        cov = nc.stored_coverage(s, ["2084", "2085"])
    c = cov["2084"]
    assert (c["in_scope"], c["labelled"], c["ok"], c["payload"]) == (3, 2, False, str(f))
    assert c["unlabelled"] == ["CFBD 9504 · 2084-09-20 Nowhere Tech @ J4 B"]          # every one, by CFBD id
    assert cov["2085"]["ok"] is False and cov["2085"]["reason"] == "no side-table rows for this season"
    out = "\n".join(nc.stored_coverage_lines(cov))
    assert "2084: labelled 2 / CFBD completed both-FBS 3 = 66.7% · >= 95%: NO" in out and "CFBD 9504" in out
    f.unlink()                                                        # the payload gone: never assumed
    with session_scope() as s:
        gone = nc.stored_coverage(s, ["2084"])["2084"]
    assert gone["ok"] is False and "unreadable" in gone["reason"]


def test_coverage_cli_prints_scope_fact_v1r_stream_and_79_info(fresh_db, tmp_path, monkeypatch):
    from click.testing import CliRunner

    import migrate_ncaa_cfbd_labels as mig
    from cli import cli
    from src.db.database import init_db, session_scope

    init_db()
    assert mig.main() == 0
    with session_scope() as s:
        _world(s)
    monkeypatch.setattr(nc, "ALIAS_FILE", tmp_path / "aliases.json")
    (tmp_path / "aliases.json").write_text(json.dumps({"aliases": {}}))
    f = tmp_path / "p.json"
    f.write_text(json.dumps(J4_RECS))
    assert nc.run([2084], from_file=str(f), out=lambda *_: None) == 0
    res = CliRunner().invoke(cli, ["ncaa-cfbd-coverage"])
    assert res.exit_code == 0, res.output
    out = res.output
    assert "SCOPE condition (ARCHITECT 2026-10-08)" in out and "coverage condition in BOTH seasons: DOES NOT HOLD" in out
    assert "2025: labelled 0 / CFBD completed both-FBS 0" in out and "no side-table rows" in out
    assert "NCAA-ELO-V1R STREAM" in out and "#79 ALL-DIVISION STREAM" in out and "SUSPENDED-PENDING-DATA" in out
