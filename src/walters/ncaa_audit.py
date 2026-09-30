"""
#79 NCAA DATA AUDIT (architect ruling 2026-09-30) — read-only.

Why it exists: the v1 gate PASSED log-loss but FAILED calibration, and the
2025 train-season home rate (0.489) is implausible for college football
(2026 test: 0.708). Before any v2, the ruling is "AUDIT FIRST: home/away
labeling and neutral sites in the 2025 pool, by stage (D2/D3 suspected);
print home rate by stage and by month for both seasons."

Stream: the SAME definition the gate uses (Sport.NFL + Competition.code
"NCAA", FINISHED, both scores present) but WITHOUT the gate's exclusions,
so the audit sees every scored row. Rows the gate would drop are printed
with the reason (nb.exclusion_reason + the tie rule), never removed here.

Law 4 (conservative unknowns): nothing here infers a neutral site or a
division. The DB stores no neutral flag and no division; the report prints
what IS stored (field inventory) and every derived signal is labelled
HEURISTIC with its threshold. This module writes NOTHING.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from src.walters import ncaa_backtest as nb

AUDIT_SEASONS = (nb.TRAIN_SEASON, nb.TEST_SEASON)

# HEURISTIC thresholds (labelled as such in every line that uses them).
ESTABLISHED_MIN_GAMES = 8     # games in THIS season in the DB; NOT a division
SUSPECT_RATE = 0.52           # stage/month home rate below this ...
SUSPECT_MIN_N = 50            # ... with at least this many games
DEFAULT_LIMIT = 20

# Match columns that are the stream itself, not candidate site/division
# indicators. Everything else on Match is enumerated in the field inventory.
_CORE_COLUMNS = {"id", "sport", "competition_id", "season", "utc_date", "status",
                 "home_team_id", "away_team_id", "home_score", "away_score"}
# Name fragments an explicit neutral-site / division column would carry.
_SITE_DIVISION_WORDS = ("neutral", "division", "conference", "round", "note",
                        "venue", "site", "location", "city", "tier", "level")


@dataclass(frozen=True)
class AuditGame:
    match_id: int
    season: str
    utc_date: datetime
    home_id: int
    away_id: int
    home_score: int
    away_score: int
    stage: str = ""

    @property
    def margin(self) -> int:
        return self.home_score - self.away_score

    @property
    def tie(self) -> bool:
        return self.home_score == self.away_score

    @property
    def home_win(self) -> bool:
        return self.home_score > self.away_score

    def gate_exclusion(self) -> str | None:
        """Why the #79 gate would drop this row (stage marker, then tie)."""
        why = nb.exclusion_reason(nb.Game(self.home_id, self.away_id, self.season,
                                          self.utc_date, self.home_score,
                                          self.away_score, self.stage))
        if why:
            return why
        return "tied final (data defect)" if self.tie else None


# --------------------------------------------------------------------------
# Pure computations
# --------------------------------------------------------------------------


@dataclass
class Row:
    key: str
    n: int = 0
    home_wins: int = 0
    ties: int = 0
    margin_sum: int = 0

    @property
    def decided(self) -> int:
        return self.n - self.ties

    @property
    def home_rate(self) -> float | None:
        """Home wins / decided games (ties out of the denominator, the gate's
        binary outcome). None when nothing decided."""
        return self.home_wins / self.decided if self.decided else None

    @property
    def mean_margin(self) -> float | None:
        return self.margin_sum / self.n if self.n else None


def _add(r: Row, g: AuditGame) -> None:
    r.n += 1
    r.home_wins += int(g.home_win)
    r.ties += int(g.tie)
    r.margin_sum += g.margin


def table(games: list[AuditGame], key: Callable[[AuditGame], str]) -> list[Row]:
    rows: dict[str, Row] = {}
    for g in games:
        k = key(g)
        _add(rows.setdefault(k, Row(k)), g)
    return [rows[k] for k in sorted(rows)]


def by_stage(games: list[AuditGame]) -> list[Row]:
    """Every distinct stage string VERBATIM; an empty/NULL stage is '<empty>'."""
    return table(games, lambda g: g.stage if g.stage else "<empty>")


def by_month(games: list[AuditGame]) -> list[Row]:
    return table(games, lambda g: g.utc_date.strftime("%Y-%m"))


def total(games: list[AuditGame], label: str = "ALL") -> Row:
    r = Row(label)
    for g in games:
        _add(r, g)
    return r


@dataclass
class Pairing:
    a: int
    b: int
    a_hosts: list[AuditGame] = field(default_factory=list)   # a listed home v b
    b_hosts: list[AuditGame] = field(default_factory=list)   # b listed home v a


def pairings(games: list[AuditGame]) -> tuple[list[Pairing], list[Pairing]]:
    """Repeated pairings within ONE season's games.
    Returns (reversed, same_way): reversed = A hosted B AND B hosted A (a
    same-season home-and-home is unusual in college football — at least one
    label may be flipped or the rematch neutral, e.g. a conference title
    game); same_way = the same host listed twice for the same pair."""
    by_pair: dict[tuple[int, int], Pairing] = {}
    for g in sorted(games, key=lambda x: (x.utc_date, x.match_id)):
        a, b = sorted((g.home_id, g.away_id))
        p = by_pair.setdefault((a, b), Pairing(a, b))
        (p.a_hosts if g.home_id == a else p.b_hosts).append(g)
    rev = [p for p in by_pair.values() if p.a_hosts and p.b_hosts]
    same = [p for p in by_pair.values()
            if (len(p.a_hosts) > 1 and not p.b_hosts) or (len(p.b_hosts) > 1 and not p.a_hosts)]
    key = lambda p: min(g.utc_date for g in p.a_hosts + p.b_hosts)
    return sorted(rev, key=key), sorted(same, key=key)


def games_per_team(games: list[AuditGame]) -> Counter:
    c: Counter = Counter()
    for g in games:
        c[g.home_id] += 1
        c[g.away_id] += 1
    return c


def home_games_per_team(games: list[AuditGame]) -> Counter:
    return Counter(g.home_id for g in games)


@dataclass
class PriorCheck:
    prior_season: str
    prior_games_in_db: int
    comparable: int = 0          # games where at least one side had a prior-season game
    home_fewer: int = 0          # provider "home" had FEWER prior-season games
    home_more: int = 0
    equal: int = 0
    neither: int = 0             # neither side in the prior season (not comparable)


def prior_season_check(games: list[AuditGame], prior_games: list[AuditGame],
                       prior_season: str) -> PriorCheck:
    """HEURISTIC (b): does the provider's 'home' team have fewer prior-season
    games in the DB than the away team? Weak signal that small programs are
    being listed as hosts. Not a division, not a site."""
    prior = games_per_team(prior_games)
    pc = PriorCheck(prior_season, len(prior_games))
    for g in games:
        h, a = prior.get(g.home_id, 0), prior.get(g.away_id, 0)
        if h == 0 and a == 0:
            pc.neither += 1
            continue
        pc.comparable += 1
        if h < a:
            pc.home_fewer += 1
        elif h > a:
            pc.home_more += 1
        else:
            pc.equal += 1
    return pc


def established_split(games: list[AuditGame], min_games: int = ESTABLISHED_MIN_GAMES,
                      counts: Counter | None = None) -> tuple[Row, Row, Row, Row]:
    """HEURISTIC (c): 'established' = >= min_games games in THIS season in the
    DB (or in `counts`, e.g. the prior season's per-team game counts — the
    variant for an in-progress season). Returns rows (both established,
    home-only established, away-only established, neither). A proxy for the
    FBS/FCS/D2-D3 suspicion — NOT a division label."""
    gp = games_per_team(games) if counts is None else counts
    est = lambda t: gp[t] >= min_games
    both = Row(f"both established (>= {min_games})")
    home_only = Row("home established, away not")
    away_only = Row("away established, home not")
    neither = Row("neither established")
    for g in games:
        h, a = est(g.home_id), est(g.away_id)
        _add(both if h and a else home_only if h else away_only if a else neither, g)
    return both, home_only, away_only, neither


def suspects(rows: list[Row], rate: float = SUSPECT_RATE,
             min_n: int = SUSPECT_MIN_N) -> list[Row]:
    return [r for r in rows if r.n >= min_n and r.home_rate is not None and r.home_rate < rate]


def home_heavy_teams(games: list[AuditGame], limit: int) -> list[tuple[int, int, int]]:
    """(team, home games, season games), highest home share first; ties on
    share broken by more season games, then team id (stable output)."""
    gp, hp = games_per_team(games), home_games_per_team(games)
    rows = [(t, hp.get(t, 0), n) for t, n in gp.items()]
    rows.sort(key=lambda x: (-x[1] / x[2], -x[2], x[0]))
    return rows[:limit]


# --------------------------------------------------------------------------
# DB loading (read-only)
# --------------------------------------------------------------------------


@dataclass
class Inventory:
    """What the DB actually stores that could speak to site or division."""
    match_columns: list[str] = field(default_factory=list)        # every Match column
    site_division_named: list[str] = field(default_factory=list)  # names matching the words
    # column -> (non-null count, distinct count, top values [(value, n)])
    match_fields: dict[str, tuple[int, int, list[tuple[str, int]]]] = field(default_factory=dict)
    external_id_keys: Counter = field(default_factory=Counter)
    team_columns: list[str] = field(default_factory=list)
    team_fields: dict[str, tuple[int, int, list[tuple[str, int]]]] = field(default_factory=dict)
    teams_total: int = 0
    status_by_season: dict[str, Counter] = field(default_factory=dict)  # ALL NCAA rows


@dataclass
class AuditData:
    games: list[AuditGame]
    names: dict[int, str]
    inventory: Inventory


def _summ(values: list, top: int) -> tuple[int, int, list[tuple[str, int]]]:
    nn = [v for v in values if v is not None and v != ""]
    c = Counter(str(v) for v in nn)
    return len(nn), len(c), c.most_common(top)


def load(top: int = DEFAULT_LIMIT) -> AuditData:
    """Read-only SELECTs only. The scored stream is the gate's (FINISHED, both
    scores, Sport.NFL + code "NCAA"); the status census covers every NCAA row."""
    from sqlalchemy import func, select

    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport, Team

    inv = Inventory()
    inv.match_columns = [c.name for c in Match.__table__.columns]
    inv.team_columns = [c.name for c in Team.__table__.columns]
    inv.site_division_named = [c for c in inv.match_columns + [f"team.{t}" for t in inv.team_columns]
                               if any(w in c.lower() for w in _SITE_DIVISION_WORDS)]
    with session_scope() as s:
        scope = (Match.sport == Sport.NFL, Competition.code == nb.NCAA_COMPETITION_CODE)
        for season, status, n in s.execute(
                select(Match.season, Match.status, func.count())
                .join(Competition, Match.competition_id == Competition.id)
                .where(*scope).group_by(Match.season, Match.status)).all():
            inv.status_by_season.setdefault(str(season), Counter())[
                getattr(status, "value", str(status))] += n
        rows = s.execute(
            select(Match).join(Competition, Match.competition_id == Competition.id)
            .where(*scope, Match.status == MatchStatus.FINISHED,
                   Match.home_score.is_not(None), Match.away_score.is_not(None))
            .order_by(Match.utc_date, Match.id)).scalars().all()
        games = [AuditGame(m.id, m.season, m.utc_date, m.home_team_id, m.away_team_id,
                           m.home_score, m.away_score, m.stage or "") for m in rows]
        for col in inv.match_columns:
            if col in _CORE_COLUMNS or col == "external_ids":
                continue
            inv.match_fields[col] = _summ([getattr(m, col) for m in rows], top)
        for m in rows:
            for k in (m.external_ids or {}):
                inv.external_id_keys[k] += 1
        team_ids = {t for g in games for t in (g.home_id, g.away_id)}
        teams = s.execute(select(Team).where(Team.id.in_(team_ids))).scalars().all() if team_ids else []
        names = {t.id: t.name for t in teams}
        inv.teams_total = len(teams)
        for col in inv.team_columns:
            if col in ("id", "sport", "name", "external_ids"):
                continue
            inv.team_fields[col] = _summ([getattr(t, col) for t in teams], top)
    return AuditData(games, names, inv)


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


def _fmt_rate(x: float | None) -> str:
    return f"{x:.3f}" if x is not None else "  n/a"


def _fmt_row(r: Row, width: int = 24) -> str:
    mm = f"{r.mean_margin:+.2f}" if r.mean_margin is not None else "n/a"
    return (f"    {r.key[:width]:<{width}} n={r.n:<5} home_wins={r.home_wins:<5} "
            f"home_rate={_fmt_rate(r.home_rate)} ties={r.ties:<3} mean_home_margin={mm}")


def _d(g: AuditGame) -> str:
    return g.utc_date.strftime("%Y-%m-%d")


def report(data: AuditData, seasons: tuple[str, ...] = AUDIT_SEASONS,
           limit: int = DEFAULT_LIMIT, out: Callable[[str], None] = print) -> None:
    games, names, inv = data.games, data.names, data.inventory
    nm = lambda t: f"{names.get(t, '?')} [{t}]"
    by_season: dict[str, list[AuditGame]] = defaultdict(list)
    for g in games:
        by_season[g.season].append(g)

    out(f"NCAA DATA AUDIT (#79, architect 2026-09-30) · read-only · stream = Sport.NFL + "
        f"code {nb.NCAA_COMPETITION_CODE!r}, FINISHED, both scores · gate exclusions NOT applied")
    out("  home_rate = home wins / decided games (ties out of the denominator); "
        "mean_home_margin = home score - away score over all n")
    out("  HEURISTIC lines are labelled; nothing here infers a neutral site or a division")
    out("CENSUS (every NCAA row, all statuses, by season)")
    for season in sorted(inv.status_by_season):
        out(f"  {season}: {dict(sorted(inv.status_by_season[season].items()))}")
    if not inv.status_by_season:
        out("  (no NCAA rows in the DB)")
    out("SCORED STREAM (finished + both scores, by season)")
    for season in sorted(by_season):
        gs = by_season[season]
        teams = {t for g in gs for t in (g.home_id, g.away_id)}
        out(f"  {season}: n={len(gs)} · {_d(gs[0])} .. {_d(gs[-1])} (UTC) · teams={len(teams)}")

    out("FIELD INVENTORY (d) — what the DB stores that could indicate a neutral site or division")
    out(f"  Match columns: {', '.join(inv.match_columns)}")
    out(f"  columns whose NAME suggests site/division ({'/'.join(_SITE_DIVISION_WORDS)}): "
        f"{', '.join(inv.site_division_named) or 'NONE'}")
    out("  NO neutral-site flag column exists on Match; NO division/conference column exists "
        "on Match or Team (schema enumerated above)")
    out(f"  Match fields over the scored stream (n={len(games)}): non-null / distinct / top values")
    for col, (nn, dc, tops) in inv.match_fields.items():
        out(f"    {col:<18} non-null={nn:<5} distinct={dc:<4} top={tops}")
    out(f"    {'external_ids keys':<18} {dict(inv.external_id_keys)}")
    out(f"  Team fields over the {inv.teams_total} programs in the stream: non-null / distinct / top")
    for col, (nn, dc, tops) in inv.team_fields.items():
        out(f"    team.{col:<13} non-null={nn:<5} distinct={dc:<4} top={tops}")

    for season in seasons:
        gs = by_season.get(season, [])
        out("")
        out(f"=== SEASON {season} === n={len(gs)}"
            + (f" · {_d(gs[0])} .. {_d(gs[-1])} (UTC)" if gs else " (no scored games)"))
        if not gs:
            continue
        out(_fmt_row(total(gs, f"ALL {season}")))
        ex = [(g, g.gate_exclusion()) for g in gs]
        ex = [(g, why) for g, why in ex if why]
        gate_kept = [g for g in gs if not g.gate_exclusion()]
        out(f"  GATE EXCLUSIONS (would be dropped by ncaa-backtest; kept here): "
            f"{dict(Counter(w for _, w in ex)) or 'none'}")
        for g, why in ex[:limit]:
            out(f"    {_d(g)} id={g.match_id} {nm(g.home_id)} {g.home_score}-{g.away_score} "
                f"{nm(g.away_id)} stage={g.stage or '<empty>'!r} -> {why}")
        if len(ex) > limit:
            out(f"    ... {len(ex) - limit} more (raise --limit)")
        out(_fmt_row(total(gate_kept, "GATE-KEPT subset")))

        stages, months = by_stage(gs), by_month(gs)
        out(f"  (1) HOME RATE BY STAGE (verbatim stage strings)")
        for r in stages:
            out(_fmt_row(r))
        out(f"  (1) HOME RATE BY MONTH (UTC year-month)")
        for r in months:
            out(_fmt_row(r))

        rev, same = pairings(gs)
        out(f"  (2a) REPEATED PAIRINGS: {len(rev)} reversed (A hosted B AND B hosted A), "
            f"{len(same)} same-host repeats")
        for p in rev[:limit]:
            legs = sorted(p.a_hosts + p.b_hosts, key=lambda x: (x.utc_date, x.match_id))
            desc = " | ".join(f"{_d(g)} {names.get(g.home_id, '?')} (home) {g.home_score}-"
                              f"{g.away_score} {names.get(g.away_id, '?')} [{g.stage or '<empty>'}]"
                              for g in legs)
            out(f"    {desc}")
        if len(rev) > limit:
            out(f"    ... {len(rev) - limit} more reversed pairings (raise --limit)")
        for p in same[:limit]:
            legs = p.a_hosts or p.b_hosts
            out(f"    same-host: {nm(legs[0].home_id)} hosted {nm(legs[0].away_id)} x{len(legs)} "
                f"on {', '.join(_d(g) for g in legs)}")
        if len(same) > limit:
            out(f"    ... {len(same) - limit} more same-host repeats (raise --limit)")

        prior_season = str(int(season) - 1) if season.isdigit() else ""
        pc = prior_season_check(gs, by_season.get(prior_season, []), prior_season)
        out(f"  (2b) HEURISTIC — provider 'home' had FEWER {prior_season} games in the DB than "
            f"the away team (a weak signal that small programs are listed as hosts; "
            f"NOT a site or division)")
        if not pc.prior_games_in_db:
            out(f"    prior season {prior_season!r}: 0 scored games in the DB — not computable")
        else:
            share = pc.home_fewer / pc.comparable if pc.comparable else None
            out(f"    prior season {prior_season!r}: {pc.prior_games_in_db} games in DB · comparable "
                f"{pc.comparable} · home fewer {pc.home_fewer} (share {_fmt_rate(share)}) · "
                f"home more {pc.home_more} · equal {pc.equal} · neither side present {pc.neither}")

        out(f"  (2c) HEURISTIC — 'established' = >= {ESTABLISHED_MIN_GAMES} games in {season} in "
            f"the DB (a proxy for the FBS/FCS/D2-D3 suspicion; the threshold is a heuristic, "
            f"NOT a division)")
        both, h_only, a_only, neither = established_split(gs)
        for r in (both, h_only, a_only, neither):
            out(_fmt_row(r, 30))
        either_not = Row(f"either side not established")
        for r in (h_only, a_only, neither):
            either_not.n += r.n
            either_not.home_wins += r.home_wins
            either_not.ties += r.ties
            either_not.margin_sum += r.margin_sum
        out(_fmt_row(either_not, 30))
        if pc.prior_games_in_db:
            out(f"    variant (HEURISTIC, for an in-progress season): 'established' = >= "
                f"{ESTABLISHED_MIN_GAMES} games in {prior_season} in the DB")
            prior_counts = games_per_team(by_season.get(prior_season, []))
            for r in established_split(gs, counts=prior_counts):
                out(_fmt_row(r, 30))

        out(f"  (3) SUSPECTS — stage/month rows with home_rate < {SUSPECT_RATE:.2f} and "
            f"n >= {SUSPECT_MIN_N}")
        sus = [("stage", r) for r in suspects(stages)] + [("month", r) for r in suspects(months)]
        for kind, r in sus:
            out(f"    {kind}:" + _fmt_row(r)[3:])
        if not sus:
            out("    none")
        out(f"  (3) TOP {limit} teams by provider-'home' share of their {season} games "
            f"(home/total; ties on share -> more games first)")
        for t, h, n in home_heavy_teams(gs, limit):
            out(f"    {nm(t):<40} home {h}/{n} = {h / n:.3f}")
