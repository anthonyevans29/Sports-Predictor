"""
NCAA SHADOW (ARCHITECT 2026-10-07, addendum 6 item 1, verbatim):
"NCAA SHADOW. Once #333's coverage receipt shows 95% on both seasons and
ncaa-elo-v1r is declared in the registry with its constants frozen, ship
export-ncaa-predictions and ncaa-shadow-grade on the NHL shadow's pattern:
engine model_shadow, the gate status on every row ('UNGATED — shadow only'
until the verdict, then the verdict), FBS games in the next 36 hours, the
market block beside each row, graded on results and on model-vs-close from
the last shadow file before kickoff. Never a call, never a venue input, never
in the ledger. The shadow starts before the gate run and changes nothing
about it: the one run, the verdict and the confirmation cohort stand as
declared, and the shadow's live record is not gate evidence. Target: the
Saturday 2026-10-10 slate. If the labels are not in by Friday night, say so
and Saturday stays market-only."

    export-ncaa-predictions  -> exports/ncaa_shadow_<YYYY-MM-DD_HHMM>.json
    ncaa-shadow-grade        -> results + model-vs-close, from the artifacts

THE PRECONDITIONS ARE CODE, NOT A CHECKLIST: the export REFUSES (exit 2,
reason stated) unless
  (a) the registry holds ncaa-elo-v1r (docs/registry/experiments.json), and
      its declaration states the neutral-site rule (NEUTRAL_RULE_KEY, one of
      NEUTRAL_RULES): "Whether v1r applies home advantage at neutral sites is
      a declaration question" (#333 ruling), so the shadow never chooses it;
  (b) the CFBD side table covers >= 95% of the gate's stream in BOTH seasons
      (ncaa_backtest.label_coverage, the #333 coverage receipt's own fact).
The architect's read of the receipt is what makes (a) happen; (b) is
re-checked on every run so a regressed side table stops the shadow.

THE MODEL IS v1 WITH ITS CONSTANTS UNTOUCHED (the #333 ruling: "ONE scored
run of v1 with its constants untouched, declared beforehand in the registry
as ncaa-elo-v1r"): src/models/ncaa_elo.NCAAEloConfig() defaults, the update
math of NCAAEloV1 verbatim. The only declared input is the neutral rule:
under "no_home_advantage_at_neutral" a game whose CFBD neutral flag is True
prices and updates with home advantage 0; an unknown flag (no side-table
row: every UPCOMING game) applies the listed home's advantage and the row
says neutral unknown (law 4). Walk-forward over the gate's stream (#333
labels applied; pre/postseason excluded; ties skipped), every game before
now, then the predictions.

ROWS: engine "model_shadow" (window card and desk_policy already skip it;
never a Desk call, never a venue input, never logged to the ledger),
model_version "ncaa_elo_v1r", competition "NCAA", family "NCAAF",
gate_verdict = "UNGATED — shadow only" until the registry records a verdict,
then that verdict. FBS = both teams appear in the CFBD side table (its
ingest's default scope is both-FBS completed games); a game with a team
outside it is skipped and counted, never priced. The market block is the
fixtures export's own (_fixture_row), beside the prediction.

GRADING READS THE ARTIFACTS: a game's call is the LAST shadow row written
before kickoff. Results: the CFBD side-table score in our orientation where
a row exists, else the matches row; hit rate, log-loss and Brier of the
shadow probability. Model-vs-close: pick-vs-close against the stored 1X2
book close (#167/#207 contract, nfl-grade's rule) and value-side-vs-close
from the earliest pre-kickoff book snapshot. The live record is NOT gate
evidence and says so.
"""
from __future__ import annotations

import contextlib
import json
import math
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from src.timeutil import utc_now_naive

ENGINE = "model_shadow"
EID = "ncaa-elo-v1r"
MODEL_VERSION = "ncaa_elo_v1r"
COMPETITION = "NCAA"
FAMILY = "NCAAF"
WINDOW_HOURS = 36
FILE_PREFIX = "ncaa_shadow_"
UNGATED = "UNGATED — shadow only"
# The declaration states one of these (the #333 ruling leaves the choice to the declaration PR).
NEUTRAL_RULE_KEY = "neutral_site_rule"
NEUTRAL_RULES = {"home_advantage_at_neutral": True, "no_home_advantage_at_neutral": False}
# Codex on #344: the declaration freezes the constants; the shadow runs only if they are v1's, untouched (#333 ruling)
CONSTANTS_KEY = "constants"
CONSTANT_KEYS = ("k_factor", "home_advantage", "mov_base", "season_regression", "default_rating")
NOTE = ("NCAA SHADOW — ncaa_elo_v1r (v1, constants untouched) as a model shadow beside the market-only NCAA "
        "Desk. Never a call, never a venue input, never in the ledger. The shadow changes nothing about the "
        "gate: the one run, the verdict and the confirmation cohort stand as declared, and this live record "
        "is NOT gate evidence.")


class ShadowRefused(RuntimeError):
    """A precondition the ruling names is not met: printed with its reason, exit 2, nothing written."""


def frozen(registry_path: str | None = None) -> tuple[dict, bool, str]:
    """(entry, home advantage at neutral sites?, rule) from the registry; refuses unless ncaa-elo-v1r is
    declared and its declaration states the neutral-site rule."""
    from src.walters import registry as reg

    e = reg.get(EID, registry_path) if registry_path else reg.get(EID)
    if e is None:
        raise ShadowRefused(f"REFUSED: {EID} is not declared in docs/registry — the NCAA shadow starts only once "
                            "it is (ARCHITECT 2026-10-07, addendum 6 item 1)")
    rule = e.get(NEUTRAL_RULE_KEY)
    if rule not in NEUTRAL_RULES:
        raise ShadowRefused(f"REFUSED: {EID}'s declaration has no {NEUTRAL_RULE_KEY} (one of "
                            f"{', '.join(sorted(NEUTRAL_RULES))}; got {rule!r}) — whether v1r applies home "
                            "advantage at neutral sites is the declaration's choice, never the shadow's")
    from src.models.ncaa_elo import NCAAEloConfig

    frozen_v1 = {k: getattr(NCAAEloConfig(), k) for k in CONSTANT_KEYS}
    declared = e.get(CONSTANTS_KEY)
    if not isinstance(declared, dict) or set(declared) != set(CONSTANT_KEYS) or any(
            not isinstance(declared[k], (int, float)) or isinstance(declared[k], bool)
            or float(declared[k]) != frozen_v1[k] for k in CONSTANT_KEYS):
        raise ShadowRefused(f"REFUSED: {EID}'s declaration must freeze {CONSTANTS_KEY} = v1's untouched constants "
                            f"{frozen_v1} (got {declared!r}) — the shadow runs only the declared model")
    return e, NEUTRAL_RULES[rule], rule


def gate_label(e: dict) -> str:
    """'UNGATED — shadow only' until the registry records a verdict, then that verdict."""
    v = (e.get("verdict") or {}).get("verdict")
    return str(v) if v else UNGATED


def coverage_guard(stream) -> dict:
    """The #333 coverage receipt's condition, re-computed: >= 95% of the stream in BOTH seasons."""
    from src.walters import ncaa_backtest as nb

    cov = nb.label_coverage(stream)
    bad = [f"{s} {nb._pct(c['covered_share'])} ({c['covered']}/{c['n']})" for s, c in cov.items()
           if not c["coverage_ok"]]
    if bad:
        raise ShadowRefused(f"REFUSED: the CFBD side table covers less than {nb.COVERAGE_MIN:.0%} of the stream in "
                            f"{'; '.join(bad)} — the shadow does not run before the coverage condition holds")
    return cov


class V1R:
    """NCAAEloV1 with its constants untouched; the declared neutral rule decides whether a CFBD-neutral game
    carries home advantage. The v1 update math is reused verbatim (the config is swapped per game)."""

    def __init__(self, neutral_home_advantage: bool):
        from src.models.ncaa_elo import NCAAEloConfig, NCAAEloV1

        self.cfg = NCAAEloConfig()
        self.m = NCAAEloV1(self.cfg)
        self.neutral_home_advantage = neutral_home_advantage
        self.neutral_updates = 0

    def home_adv(self, g) -> float:
        if not self.neutral_home_advantage and getattr(g, "neutral", None) is True:
            return 0.0
        return self.cfg.home_advantage

    @contextlib.contextmanager
    def _for(self, g):
        ha = self.home_adv(g)
        if ha == self.cfg.home_advantage:
            yield
            return
        self.m.cfg = replace(self.cfg, home_advantage=ha)
        try:
            yield
        finally:
            self.m.cfg = self.cfg

    def predict(self, g) -> float:
        with self._for(g):
            return self.m.predict(g)

    def update(self, g) -> None:
        if getattr(g, "neutral", None) is True:
            self.neutral_updates += 1
        with self._for(g):
            self.m.update(g)

    def rating(self, team_id: int) -> float:
        return self.m.rating(team_id)


def fit(now: datetime, neutral_home_advantage: bool, games=None):
    """(model, receipt): walk-forward over the gate's stream (labels applied) before `now`; refuses unless the
    coverage condition holds."""
    from src.walters import ncaa_backtest as nb

    st = nb.build_stream(nb.load_games() if games is None else games)
    cov = coverage_guard(st)
    model = V1R(neutral_home_advantage)
    used = 0
    for g in sorted(st.train + st.test, key=lambda x: x.utc_date):
        if g.utc_date >= now:
            continue
        model.update(g)
        used += 1
    return model, {"games_used": used, "train_n": len(st.train), "test_n": len(st.test),
                   "excluded": {f"{s}/{why}": n for (s, why), n in sorted(st.excluded.items())},
                   "ties_skipped": st.ties, "neutral_updates": model.neutral_updates,
                   "coverage": {s: round(c["covered_share"], 4) for s, c in cov.items()},
                   "constants": {"k_factor": model.cfg.k_factor, "home_advantage": model.cfg.home_advantage,
                                 "mov_base": model.cfg.mov_base, "season_regression": model.cfg.season_regression,
                                 "default_rating": model.cfg.default_rating}}


def fbs_teams(s) -> set[int]:
    """Teams that appear in the CFBD side table (its ingest's default scope: both-FBS completed games)."""
    from sqlalchemy import select

    from src.db.schema import Match, NCAACFBDLabel

    q = select(Match.home_team_id, Match.away_team_id).join(NCAACFBDLabel, NCAACFBDLabel.match_id == Match.id)
    return {t for row in s.execute(q).all() for t in row}


def build_rows(now: datetime | None = None, hours: int = WINDOW_HOURS, registry_path: str | None = None) -> dict:
    from collections import Counter

    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Competition, Match, MatchStatus, Sport
    from src.walters import ncaa_backtest as nb
    from src.walters.export import _fixture_row

    now = now or utc_now_naive()
    e, neutral_ha, rule = frozen(registry_path)
    label = gate_label(e)
    model, rc = fit(now, neutral_ha)
    rc["neutral_site_rule"] = rule
    rows, skipped = [], Counter()
    with session_scope() as s:
        fbs = fbs_teams(s)
        q = (select(Match).join(Competition, Match.competition_id == Competition.id)
             .where(Match.sport == Sport.NFL, Competition.code == COMPETITION,
                    Match.status == MatchStatus.SCHEDULED,
                    Match.utc_date >= now, Match.utc_date < now + timedelta(hours=hours))
             .order_by(Match.utc_date, Match.id))
        for m in s.execute(q).scalars():
            g = nb.Game(m.home_team_id, m.away_team_id, m.season, m.utc_date, 0, 0, m.stage or "", match_id=m.id)
            why = nb.exclusion_reason(g)
            if why:
                skipped[why] += 1
                continue
            if m.home_team_id not in fbs or m.away_team_id not in fbs:
                skipped["not_both_fbs"] += 1
                continue
            p = model.predict(g)
            row = _fixture_row(s, m, COMPETITION, Counter(), Counter())
            pick_home = p >= 0.5
            row.update({
                "competition": COMPETITION, "family": FAMILY,
                "engine": ENGINE, "model_version": MODEL_VERSION, "gate_verdict": label, "registry_id": EID,
                "prediction": {"home_win_prob": round(p, 4), "away_win_prob": round(1 - p, 4),
                               "top_pick": "home_win" if pick_home else "away_win",
                               "top_pick_prob": round(p if pick_home else 1 - p, 4),
                               "elo_home": round(model.rating(m.home_team_id), 1),
                               "elo_away": round(model.rating(m.away_team_id), 1),
                               "home_adv_applied": model.home_adv(g),
                               "neutral": None},          # unknown before the game (no side-table row): law 4
            })
            rows.append(row)
        s.rollback()
    return {"rows": rows, "fit": rc, "skipped": dict(skipped), "label": label, "now": now}


def export(now: datetime | None = None, hours: int = WINDOW_HOURS, out_dir: str = "exports",
           registry_path: str | None = None) -> tuple[str, dict]:
    r = build_rows(now, hours, registry_path)
    now = r["now"]
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    # Codex on #344: second precision and an exclusive create, so a rerun never replaces an earlier artifact
    path = str(Path(out_dir) / f"{FILE_PREFIX}{now.strftime('%Y-%m-%d_%H%M%S')}.json")
    doc = {"sport": "ncaa", "competition": COMPETITION, "family": FAMILY, "engine": ENGINE,
           "model_version": MODEL_VERSION, "registry_id": EID, "gate_verdict": r["label"],
           "contains_predictions": False,   # nothing here is a live prediction (doctrine)
           "gate_evidence": False,          # the shadow's live record is not gate evidence (ruling)
           "exported_at": now.isoformat(), "window_hours": hours, "note": NOTE,
           "fit": r["fit"], "skipped": r["skipped"], "count": len(r["rows"]), "predictions": r["rows"]}
    try:
        with open(path, "x") as f:
            json.dump(doc, f, indent=2, default=str)
    except FileExistsError:
        raise ShadowRefused(f"REFUSED: {path} already exists — an artifact is never overwritten; re-run next second")
    return path, doc


def last_calls(export_dir: str = "exports") -> dict[int, dict]:
    """match_id -> the LAST shadow row written before its kickoff."""
    out: dict[int, dict] = {}
    for f in sorted(Path(export_dir).glob(f"{FILE_PREFIX}*.json")):
        try:
            doc = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if doc.get("engine") != ENGINE or doc.get("competition") != COMPETITION:
            continue
        at = doc.get("exported_at") or ""
        for r in doc.get("predictions") or []:
            mid, ko = r.get("match_id"), r.get("utc_date") or ""
            if mid is None or not at or at >= ko:
                continue
            if mid not in out or at >= out[mid]["exported_at"]:
                out[mid] = {**r, "exported_at": at, "source_file": f.name}
    return out


def _result(s, m) -> tuple[int, int, str] | None:
    """(home score, away score, source) in OUR orientation: the CFBD side table where a row exists (the label
    source of record stores the source's scores in our orientation), else the matches row."""
    from sqlalchemy import inspect

    from src.db.schema import NCAACFBDLabel

    if inspect(s.connection()).has_table(NCAACFBDLabel.__tablename__):
        lab = s.get(NCAACFBDLabel, m.id)
        if lab is not None and lab.orientation in ("same", "swapped"):
            return lab.home_score, lab.away_score, "cfbd"
    if m.home_score is None or m.away_score is None:
        return None
    return m.home_score, m.away_score, "matches"


def grade(days: int = 30, export_dir: str = "exports", now: datetime | None = None, progress=None) -> dict:
    """Results (hit rate, log-loss, Brier) and model-vs-close (pick-vs-close + value-side) for finished NCAA
    games whose call exists in a shadow export. Not gate evidence."""
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Match, MatchStatus, Odds
    from src.walters.close import close_1x2, outcomes_for, priced
    from src.walters.nfl_predict import _book_anchor, value_side_grade

    now = now or utc_now_naive()
    calls = last_calls(export_dir)
    hits, lls, briers, clvs, vclvs, lines = [], [], [], [], [], []
    graded = unpriced = unanchored = ties = no_result = identity_mismatch = 0
    with session_scope() as s:
        for mid, c in sorted(calls.items(), key=lambda kv: kv[1].get("utc_date") or ""):
            m = s.get(Match, mid)
            if m is None or m.status != MatchStatus.FINISHED or m.utc_date < now - timedelta(days=days):
                continue
            # Codex on #344: match ids are machine-local and reusable (init-db --force); the artifact row's teams and
            # kickoff must be this match's, else it is never graded against it
            if (m.competition is None or m.competition.code != COMPETITION
                    or (c.get("home_team"), c.get("away_team")) != (m.home_team.name, m.away_team.name)
                    or c.get("utc_date") != m.utc_date.isoformat()):
                identity_mismatch += 1
                continue
            res = _result(s, m)
            if res is None:
                no_result += 1
                continue
            hs, as_, src = res
            if hs == as_:
                ties += 1                                   # college football cannot tie: a data defect
                continue
            graded += 1
            p = c["prediction"]["home_win_prob"]
            y = 1 if hs > as_ else 0
            pick_home = p >= 0.5
            hits.append(1 if pick_home == bool(y) else 0)
            pc = min(max(p, 1e-12), 1 - 1e-12)
            lls.append(-(y * math.log(pc) + (1 - y) * math.log(1 - pc)))
            briers.append((p - y) ** 2)
            odds = list(s.execute(select(Odds).where(Odds.match_id == m.id, Odds.market == "1X2")).scalars())
            cl = close_1x2(odds, m.utc_date, outcomes_for(m.sport))
            close_h = cl["fair"].get("HOME", 0) if priced(cl) else None
            clv = None
            if close_h is not None:
                clv = (p if pick_home else 1 - p) - (close_h if pick_home else 1 - close_h)
                clvs.append(clv)
            else:
                unpriced += 1
            anchor_h, _ = _book_anchor(s, m)
            vg = value_side_grade(p, anchor_h, close_h)
            if vg:
                vclvs.append(vg["value_side_clv"])
            elif anchor_h is None:
                unanchored += 1
            line = (f"  {m.away_team.name[:16]:16} @ {m.home_team.name[:16]:16} v1r_H={p:.3f} "
                    f"result {hs}-{as_} ({src}) {'HIT' if hits[-1] else 'miss'} · "
                    f"close_H={'%.3f' % close_h if close_h is not None else '  — '} "
                    f"div={'%+.1fpp' % (clv * 100) if clv is not None else '—'} "
                    f"value={(vg['side'] + ' %+.1fpp' % (vg['value_side_clv'] * 100)) if vg else '— (no anchor)'}"
                    " · NOT gate evidence")
            lines.append(line)
            if progress:
                progress(line)
    return {"graded": graded, "calls_on_file": len(calls), "ties_skipped": ties, "no_result": no_result,
            "identity_mismatch": identity_mismatch,
            "hit_rate": round(sum(hits) / len(hits), 4) if hits else None,
            "log_loss": round(sum(lls) / len(lls), 4) if lls else None,
            "brier": round(sum(briers) / len(briers), 4) if briers else None,
            "priced": len(clvs), "unpriced": unpriced,
            "mean_clv_pp": round(sum(clvs) / len(clvs) * 100, 2) if clvs else None,
            "value_side_n": len(vclvs), "unanchored": unanchored,
            "mean_value_side_clv_pp": round(sum(vclvs) / len(vclvs) * 100, 2) if vclvs else None,
            "lines": lines}
