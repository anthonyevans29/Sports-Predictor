"""THE PROVIDER'S ANSWER WHEN BOOKS ARE 0 (ARCHITECT 2026-10-16, addendum 97 item 2, #550/#514).

(a) "the closing file's MLB books line says WHY when n is 0: "books: provider listed the game, no odds" (from the sync
step's own answer, which the run already has) rather than a bare count; the closing-file schema gains that string field
(null when books exist); a test on the 10-15 shape." (b) "A tally line in mlb-actionable-receipt's postseason split:
"closing runs with no provider odds: N of M" — read-only".

The 10-15 shape (addendum 97 item 1): at T-35m the provider still LISTED Milwaukee at Los Angeles (game 190164) WITHOUT
odds: "rollover fallback: 1 upcoming games with no odds — trying per-game requests… · provider has no odds yet for
Milwaukee Brewers @ Los Angeles Dodgers (game 190164)"; the step exited 0 and stored nothing; the row read books n 0."""
import io
import json
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace as NS

from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Sport, Team
from src.timeutil import utc_now_naive
from tests.test_closing_runs import NOW, at, box, c, mc, runs  # noqa: F401  (box is a fixture)

LISTED = "provider listed the game, no odds"


class FakeBaseball:
    """API-Baseball as sync_odds_mlb reads it: a bulk window (by default one game we do not store, so the fallback
    runs), a games listing per date (or a failed listing read), and per-game odds."""
    requests_remaining = 9

    def __init__(self, listing, odds, window=None, listing_error=None):
        self.listing, self.odds, self.asked, self.listing_error = listing, odds, [], listing_error
        self.window = window if window is not None else [ow("NBO Nowhere", "NBO Elsewhere", "HOME", 1.9, days=3)]

    def list_odds_window(self, season):
        return self.window

    def list_games_on_date(self, season, date_str):
        if self.listing_error:
            from src.adapters.api_baseball import APIBaseballError
            raise APIBaseballError(self.listing_error)
        return self.listing

    def list_odds_for_game(self, season, game_id):
        self.asked.append(game_id)
        return self.odds.get(game_id, [])


def ow(home, away, sel, px, hours=2, days=0, book="bk", gid=1):
    return NS(api_baseball_game_id=gid, home_team=home, away_team=away,
              commence_time=utc_now_naive() + timedelta(days=days, hours=hours), market="1X2", selection=sel,
              bookmaker=book, price_decimal=px, line=None)


def _games(tag, **fake):
    """Three SCHEDULED MLB games inside the fallback's 12 hours, with no odds stored: the 10-15 shape (listed, no
    odds), a game the provider's listing does not hold, and a game it prices. `tag` keeps each test's teams apart
    (the throwaway DB is shared by the session)."""
    init_db()
    ko = utc_now_naive() + timedelta(hours=2)
    names = {"listed": (f"{tag} Dodgers", f"{tag} Brewers"), "unmatched": (f"{tag} Guardians", f"{tag} Rays"),
             "priced": (f"{tag} Phillies", f"{tag} Braves")}
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "MLB")).scalars().first()
        if comp is None:
            comp = Competition(sport=Sport.MLB, code="MLB", name="Major League Baseball", area="USA", type="LEAGUE")
            s.add(comp)
            s.flush()
        ids = {}
        for key, (home, away) in names.items():
            h, a = Team(sport=Sport.MLB, name=home), Team(sport=Sport.MLB, name=away)
            s.add_all([h, a])
            s.flush()
            m = Match(sport=Sport.MLB, competition_id=comp.id, season="2026", utc_date=ko,
                      status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id)
            s.add(m)
            s.flush()
            ids[key] = m.id
    when = ko.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    listing = [{"id": gid, "date": when, "teams": {"home": {"name": names[k][0]}, "away": {"name": names[k][1]}}}
               for gid, k in ((190164, "listed"), (190170, "priced"))]
    books = [NS(market="1X2", selection=sel, bookmaker=f"bk{i}", price_decimal=px, line=None)
             for i in range(8) for sel, px in (("HOME", 1.8), ("AWAY", 2.05))]
    return ids, names, FakeBaseball(listing, {190170: books}, **fake)


def _sync(monkeypatch, fake):
    from src.adapters import api_baseball
    from src.ingestion.service import IngestionService
    monkeypatch.setattr(api_baseball.APIBaseballClient, "from_env", classmethod(lambda cls: fake))
    logged = []
    res = IngestionService(NS(source_name="mlb_stats_api")).sync_odds_mlb(season=2026, on_log=logged.append)
    return res, logged


def _line(res):
    import cli
    buf = io.StringIO()
    with redirect_stdout(buf):
        cli._print_no_book_odds(res)
    return buf.getvalue().strip()


SYNC_ARGV = ["sync-odds", "--competition", "MLB", "--season", "2026"]


def test_the_mlb_sync_names_each_game_it_left_with_no_book_odds_and_the_closing_run_reads_its_line(monkeypatch):
    """The sync's own answer, recorded on the result and printed as one plain line (the step's last), which the
    closing run reads by match id: the 10-15 game as "provider listed the game, no odds"."""
    import cli
    from src.ingestion.service import NO_BOOK_ODDS_WHY

    ids, names, fake = _games("NBA1")
    res, logged = _sync(monkeypatch, fake)
    mine = {g["match_id"]: g for g in res.no_book_odds if g["match_id"] in ids.values()}
    assert mine == {ids["listed"]: {"match_id": ids["listed"], "game": "NBA1 Brewers @ NBA1 Dodgers",
                                    "game_id": 190164, "answer": "listed"},
                    ids["unmatched"]: {"match_id": ids["unmatched"], "game": "NBA1 Rays @ NBA1 Guardians",
                                       "game_id": None, "answer": "unmatched"}}      # the priced game: not named
    assert "    · provider has no odds yet for NBA1 Brewers @ NBA1 Dodgers (game 190164)" in logged   # as before
    assert NO_BOOK_ODDS_WHY["listed"] == LISTED and res.no_book_odds_run is None
    line = _line(res)
    assert line.startswith("NO-BOOK-ODDS (MLB): ") and "\n" not in line
    assert f"match {ids['listed']} [{LISTED}] NBA1 Brewers @ NBA1 Dodgers (game 190164)" in line
    assert f"match {ids['unmatched']} [no game in the provider's listing matched it] NBA1 Rays @ NBA1 Guardians" in line
    assert mc.NO_BOOK_ODDS_MARK == cli.NO_BOOK_ODDS_MARK
    got = mc.no_book_odds(SYNC_ARGV, ["✓ MLB odds: ...", line])
    assert got[ids["listed"]] == LISTED and mc.RUN_KEY not in got
    assert mc.no_book_odds(["sync-kalshi"], [line]) == {}                          # only the sync-odds step's line
    assert _line(NS(no_book_odds=[], no_book_odds_run=None)) == ""                 # every game priced: no line


def test_a_failed_listing_read_is_never_read_as_the_game_not_listed(monkeypatch):
    """Review before #563: a games listing that failed is its own answer, never "not listed" (law 4)."""
    ids, _, fake = _games("NBA2", listing_error="GET /games: HTTP 500")
    res, logged = _sync(monkeypatch, fake)
    mine = {g["match_id"]: g["answer"] for g in res.no_book_odds if g["match_id"] in ids.values()}
    assert mine == {ids["listed"]: "listing_failed", ids["unmatched"]: "listing_failed",
                    ids["priced"]: "listing_failed"}
    assert any("✗ games listing" in x for x in logged)
    assert f"match {ids['listed']} [the provider's games listing read failed]" in _line(res)


def test_a_bulk_matched_game_stored_with_no_complete_book_is_named(monkeypatch):
    """Review before #563: the bulk window gives a covered game one side only; it is stored, so the fallback never
    asks it again, and the sync names it "provider odds stored, no complete book"."""
    ids, names, fake = _games("NBA3")
    home, away = names["priced"]
    fake.window = [ow(home, away, "HOME", 1.8, book=f"bk{i}", gid=777) for i in range(3)]   # HOME side only
    res, _ = _sync(monkeypatch, fake)
    got = {g["match_id"]: g for g in res.no_book_odds if g["match_id"] in ids.values()}
    assert got[ids["priced"]]["answer"] == "incomplete" and got[ids["priced"]]["game_id"] == 777
    assert f"match {ids['priced']} [provider odds stored, no complete book]" in _line(res)


def test_when_the_fallback_never_runs_the_run_gives_its_own_answer(monkeypatch):
    """Review before #563: an empty odds window (or a failed window read, or no key) returns before the per-game
    fallback. The line carries the run's answer, and the closing file gives it to every row with no book and no
    answer of its own; a row with books keeps why null."""
    from src.ingestion.service import NO_BOOK_ODDS_RUN_WHY

    _, _, fake = _games("NBA4", window=[])
    res, _ = _sync(monkeypatch, fake)
    assert res.no_book_odds == [] and res.no_book_odds_run == "window_empty"
    line = _line(res)
    assert line == f"NO-BOOK-ODDS (MLB): run [{NO_BOOK_ODDS_RUN_WHY['window_empty']}]"
    got = mc.no_book_odds(SYNC_ARGV, ["✓ MLB odds: created=0 updated=0 skipped=0", line])
    assert got == {mc.RUN_KEY: NO_BOOK_ODDS_RUN_WHY["window_empty"]}
    doc = {"predictions": [{"match_id": 1, "market": {"bookmaker_count": 0}},
                           {"match_id": 2, "market": {"bookmaker_count": 0}},
                           {"match_id": 3, "market": {"bookmaker_count": 7}}]}
    books = mc.closing_doc(doc, "MLB", mc.parse_utc("2026-10-15T23:00:00Z"), "R", [1, 2, 3], [],
                           books_why={**got, 2: LISTED})["closing"]["books"]
    assert [b["why"] for b in books] == [NO_BOOK_ODDS_RUN_WHY["window_empty"], LISTED, None]
    assert _line(NS(no_book_odds=[], no_book_odds_run="window_failed")).endswith(
        f"run [{NO_BOOK_ODDS_RUN_WHY['window_failed']}]")


def test_sync_odds_prints_the_line_last_so_the_step_tail_carries_it(monkeypatch):
    """The wiring: `sync-odds --competition MLB` ends with the NO-BOOK-ODDS line, inside sp_run's five-line tail."""
    import cli
    from click.testing import CliRunner

    ids, _, fake = _games("NBA5")
    from src.adapters import api_baseball
    monkeypatch.setattr(api_baseball.APIBaseballClient, "from_env", classmethod(lambda cls: fake))
    out = CliRunner().invoke(cli.cli, SYNC_ARGV)
    assert out.exit_code == 0, out.output
    lines = [x for x in out.output.splitlines() if x.strip()]
    assert lines[-1].startswith("NO-BOOK-ODDS (MLB): ")
    assert mc.no_book_odds(SYNC_ARGV, lines[-mc.sp_run.TAIL:])[ids["listed"]] == LISTED


def _tail_1015(mid):
    """The closing run's sync-odds step at T-35m on 10-15, its last five lines (sp_run.TAIL), with the new line."""
    return ["  rollover fallback: 1 upcoming games with no odds — trying per-game requests…",
            "    · provider has no odds yet for Kalshiburg Visitors @ Kalshiburg (game 190164)",
            "  rollover fallback: filled 0/1",
            "sync_odds_mlb: created=0 games=0 skipped=0",
            "✓ MLB odds: created=0 updated=0 skipped=0",
            f"NO-BOOK-ODDS (MLB): 1 game(s) with no book odds: match {mid} [{LISTED}] Kalshiburg Visitors @ "
            "Kalshiburg (game 190164)"][-5:]


def test_the_10_15_shape_the_closing_files_books_line_says_why(box):
    """Match 104 is the frame's no-book row (market.bookmaker_count 0, Kalshi only), 50547's shape. Its run's sync
    step named it listed with no odds: the closing block's books entry says so; a row with books has why null; the
    rows stay as the export gave them; the receipt's step records the answer."""
    box.tails["sync-odds"] = _tail_1015(104)
    assert mc.run("MLB", start=at(30), now=NOW) == 0
    r = runs("MLB")[-1]
    doc = json.loads((box.repo / r["closing_file"]["file"]).read_text())
    books = {b["match_id"]: b for b in doc["closing"]["books"]}
    assert books[104] == {"match_id": 104, "n": 0, "why": LISTED}
    assert all(b["why"] is None and b["n"] == 9 for mid, b in books.items() if mid != 104)
    assert [b["match_id"] for b in doc["closing"]["books"]] == doc["closing"]["match_ids"]
    exported = {p["match_id"]: p for p in box.docs["MLB"]["predictions"]}
    assert all(p == exported[p["match_id"]] for p in doc["predictions"])               # rows untouched
    step = next(x for x in r["steps"] if x["command"].startswith("python cli.py sync-odds"))
    assert step["no_book_odds"] == {"104": LISTED}


def test_a_no_book_row_the_sync_did_not_name_is_never_given_a_reason(box):
    """Law 4: a row with no book whose run's sync step named no answer for it says so, never a guess."""
    assert mc.run("MLB", start=at(30), now=NOW) == 0
    doc = json.loads((box.repo / runs("MLB")[-1]["closing_file"]["file"]).read_text())
    assert {b["match_id"]: b["why"] for b in doc["closing"]["books"]}[104] == mc.BOOKS_NO_ANSWER


def test_only_mlb_closing_files_carry_the_books_line_and_the_backfill_is_unchanged():
    doc = {"sport": "nfl", "predictions": [{"match_id": 1, "market": {"bookmaker_count": 0}}]}
    start = mc.parse_utc("2026-10-15T23:00:00Z")
    assert "books" not in mc.closing_doc(doc, "NFL", start, "R", [1], [], books_why={})["closing"]
    assert "books" not in mc.closing_doc(doc, "MLB", start, "R", [1], [])["closing"]  # the backfill's call
    assert mc.closing_doc(doc, "MLB", start, "R", [1], [], books_why={1: LISTED})["closing"]["books"] == [
        {"match_id": 1, "n": 0, "why": LISTED}]


def test_the_actionable_receipt_tallies_postseason_closing_runs_with_no_provider_odds(tmp_path):
    """(b): "closing runs with no provider odds: N of M", read from the closing files and the DB's stage."""
    from src.walters import mlb_actionable as MA

    init_db()
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "MLB")).scalars().first()
        if comp is None:
            comp = Competition(sport=Sport.MLB, code="MLB", name="Major League Baseball", area="USA", type="LEAGUE")
            s.add(comp)
            s.flush()
        h, a = Team(sport=Sport.MLB, name="NBT Home"), Team(sport=Sport.MLB, name="NBT Away")
        s.add_all([h, a])
        s.flush()
        mids = {}
        for tag, stage, season in (("ld1", "D", "2091"), ("ld2", "D", "2091"), ("ld3", "L", "2091"),
                                   ("reg", "R", "2091"), ("old", "D", "2090")):
            m = Match(sport=Sport.MLB, competition_id=comp.id, season=season, utc_date=utc_now_naive(),
                      status=MatchStatus.FINISHED, home_team_id=h.id, away_team_id=a.id, stage=stage)
            s.add(m)
            s.flush()
            mids[tag] = m.id
    ex = tmp_path / "exports"
    ex.mkdir()

    def close(name, *rows):
        (ex / f"closing_MLB_{name}.json").write_text(json.dumps({"predictions": [
            {"match_id": mids[t], "market": {"bookmaker_count": n}} for t, n in rows]}))
    close("2091-10-11T0000Z", ("ld1", 0))                       # the #514 shape: no book
    close("2091-10-12T0000Z", ("ld2", 8))
    close("2091-10-16T0000Z", ("ld3", 0), ("ld2", 9))           # two games, one with no book: the run counts once
    close("2091-08-01T2300Z", ("reg", 0))                       # regular season: not in the postseason split
    close("2090-10-10T0000Z", ("old", 0))                       # another season
    (ex / "closing_NFL_2091-10-12T1700Z.json").write_text(json.dumps({"predictions": [{"match_id": mids["ld1"]}]}))
    (ex / "closing_MLB_2091-10-17T0000Z.json").write_text("{not json")
    with session_scope() as s:
        t = MA.closing_tally(s, "2091", ex)
    assert (t["no_odds"], t["runs"], t["games_no_odds"], t["games"]) == (2, 3, 2, 4)
    assert t["no_odds_files"] == ["closing_MLB_2091-10-11T0000Z.json", "closing_MLB_2091-10-16T0000Z.json"]
    assert t["unreadable"] == ["closing_MLB_2091-10-17T0000Z.json"]
    res = MA.receipt([], b=10)
    res["closing_tally"] = t
    text_ = MA.format_receipt(res, season="2091", run_stamp="X")
    post = text_.split("## Postseason (stage F/D/L/W)", 1)[1].split("\n## ", 1)[0]
    assert "- closing runs with no provider odds: 2 of 3" in post                 # in the postseason split
    assert "games: 2 of 4" in post and "unreadable files 1" in post
    assert "closing runs with no provider odds" not in text_.split("## Postseason (stage F/D/L/W)", 1)[0]


def test_the_receipt_command_prints_the_tally_in_its_postseason_split(monkeypatch, tmp_path):
    """The wiring: `mlb-actionable-receipt` reads the closing files under the checkout's exports/ and its written
    receipt carries the tally line inside the postseason split."""
    import cli
    from click.testing import CliRunner
    from src.walters import mlb_actionable as MA

    seen = []

    def tally(s, season, exports_dir):
        seen.append((season, exports_dir))
        return {"runs": 3, "no_odds": 2, "no_odds_files": ["closing_MLB_x.json"], "games": 4, "games_no_odds": 2,
                "unreadable": []}
    monkeypatch.setattr(MA, "closing_tally", tally)
    out = tmp_path / "r.md"
    res = CliRunner().invoke(cli.cli, ["mlb-actionable-receipt", "--season", "2091", "--out", str(out)])
    assert res.exit_code == 0, res.output
    assert seen == [("2091", Path(cli.__file__).resolve().parent / "exports")]
    post = out.read_text().split("## Postseason (stage F/D/L/W)", 1)[1].split("\n## ", 1)[0]
    assert "- closing runs with no provider odds: 2 of 3" in post
