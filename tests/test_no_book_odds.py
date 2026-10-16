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
from types import SimpleNamespace as NS

from sqlalchemy import select

from src.db.database import init_db, session_scope
from src.db.schema import Competition, Match, MatchStatus, Sport, Team
from src.timeutil import utc_now_naive
from tests.test_closing_runs import NOW, at, box, c, mc, runs  # noqa: F401  (box is a fixture)

LISTED = "provider listed the game, no odds"


class FakeBaseball:
    """API-Baseball as sync_odds_mlb reads it: a bulk window holding one game we do not store (so the fallback runs),
    a games listing per date, and per-game odds."""
    requests_remaining = 9

    def __init__(self, listing, odds):
        self.listing, self.odds, self.asked = listing, odds, []

    def list_odds_window(self, season):
        return [NS(api_baseball_game_id=1, home_team="NBO Nowhere", away_team="NBO Elsewhere",
                   commence_time=utc_now_naive() + timedelta(days=3), market="1X2", selection="HOME",
                   bookmaker="bk", price_decimal=1.9, line=None)]

    def list_games_on_date(self, season, date_str):
        return self.listing

    def list_odds_for_game(self, season, game_id):
        self.asked.append(game_id)
        return self.odds.get(game_id, [])


def _games():
    """Three SCHEDULED MLB games inside the fallback's 12 hours, with no odds stored: the 10-15 shape (listed, no
    odds), a game the provider does not list, and a game it prices."""
    init_db()
    ko = utc_now_naive() + timedelta(hours=2)
    with session_scope() as s:
        comp = s.execute(select(Competition).where(Competition.code == "MLB")).scalars().first()
        if comp is None:
            comp = Competition(sport=Sport.MLB, code="MLB", name="Major League Baseball", area="USA", type="LEAGUE")
            s.add(comp)
            s.flush()
        ids = {}
        for tag, (home, away) in {"listed": ("NBO Dodgers", "NBO Brewers"), "unlisted": ("NBO Guardians", "NBO Rays"),
                                  "priced": ("NBO Phillies", "NBO Braves")}.items():
            h, a = Team(sport=Sport.MLB, name=home), Team(sport=Sport.MLB, name=away)
            s.add_all([h, a])
            s.flush()
            m = Match(sport=Sport.MLB, competition_id=comp.id, season="2026", utc_date=ko,
                      status=MatchStatus.SCHEDULED, home_team_id=h.id, away_team_id=a.id)
            s.add(m)
            s.flush()
            ids[tag] = m.id
    when = (ko).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    listing = [{"id": gid, "date": when, "teams": {"home": {"name": h}, "away": {"name": a}}}
               for gid, h, a in ((190164, "NBO Dodgers", "NBO Brewers"), (190170, "NBO Phillies", "NBO Braves"))]
    books = [NS(market="1X2", selection=sel, bookmaker=f"bk{i}", price_decimal=px, line=None)
             for i in range(8) for sel, px in (("HOME", 1.8), ("AWAY", 2.05))]
    return ids, FakeBaseball(listing, {190170: books})


def test_the_mlb_sync_names_each_game_it_left_with_no_book_odds_and_the_closing_run_reads_its_line(monkeypatch):
    """The sync's own answer, recorded on the result and printed as one plain line (the step's last), which the
    closing run reads by match id: the 10-15 game as "provider listed the game, no odds"."""
    import cli
    from src.adapters import api_baseball
    from src.ingestion.service import NO_BOOK_ODDS_WHY, IngestionService

    ids, fake = _games()
    monkeypatch.setattr(api_baseball.APIBaseballClient, "from_env", classmethod(lambda cls: fake))
    logged = []
    res = IngestionService(NS(source_name="mlb_stats_api")).sync_odds_mlb(season=2026, on_log=logged.append)
    mine = {g["match_id"]: g for g in res.no_book_odds if g["match_id"] in ids.values()}
    assert mine == {ids["listed"]: {"match_id": ids["listed"], "game": "NBO Brewers @ NBO Dodgers",
                                    "game_id": 190164, "answer": "listed"},
                    ids["unlisted"]: {"match_id": ids["unlisted"], "game": "NBO Rays @ NBO Guardians",
                                      "game_id": None, "answer": "unlisted"}}            # the priced game: not named
    assert "    · provider has no odds yet for NBO Brewers @ NBO Dodgers (game 190164)" in logged   # as before
    assert NO_BOOK_ODDS_WHY["listed"] == LISTED
    buf = io.StringIO()
    with redirect_stdout(buf):
        cli._print_no_book_odds(res)
    line = buf.getvalue().strip()
    assert line.startswith("NO-BOOK-ODDS (MLB): ") and "\n" not in line
    assert f"match {ids['listed']} [{LISTED}] NBO Brewers @ NBO Dodgers (game 190164)" in line
    assert f"match {ids['unlisted']} [provider did not list the game] NBO Rays @ NBO Guardians" in line
    assert mc.NO_BOOK_ODDS_MARK == cli.NO_BOOK_ODDS_MARK
    got = mc.no_book_odds(["sync-odds", "--competition", "MLB", "--season", "2026"], ["✓ MLB odds: ...", line])
    assert got[ids["listed"]] == LISTED and got[ids["unlisted"]] == "provider did not list the game"
    assert mc.no_book_odds(["sync-kalshi"], [line]) == {}                          # only the sync-odds step's line
    buf = io.StringIO()
    with redirect_stdout(buf):
        cli._print_no_book_odds(NS(no_book_odds=[]))
    assert buf.getvalue() == ""                                                   # every game priced: no line


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
