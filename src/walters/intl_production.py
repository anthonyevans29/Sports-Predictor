"""
INTERNATIONALS PRODUCTION EXPORT — built DARK (ARCHITECT 2026-10-07, item 4):
"Build dark; nothing changes for anyone until registry.production_allowed("intl-elo-v2") is true."
"a. the production export path for senior competitive internationals: desk blocks ONLY when production_allowed is
true; rows carry market_divergence_pp and quarantine as the NFL export defines them; until then
export-unl-predictions stays the shadow, unchanged."

    export-intl-predictions  -> exports/intl_predictions_<YYYY-MM-DD_HHMM>.json   (REFUSED until CONFIRMED)

- REFUSES (writes nothing) unless registry.production_allowed("intl-elo-v2") is true: a PASS verdict AND a recorded
  CONFIRMED confirmation. Until then the UNL shadow (export-unl-predictions, src/walters/intl_shadow.py) is the only
  intl model file, and it is untouched by this module.
- The model is the shadow's, exactly: intl_shadow.build_rows (intl-elo-v2 as run, registry multipliers, neutral
  rule v3, walk-forward to now). This module only re-shapes its rows for the Desk.
- Each row carries, as the NFL export defines them (src/walters/nfl_predict.py):
    market_divergence_pp = (model HOME p − book fair HOME) × 100, 1 dp, from the 1X2 close; null when unpriced;
    quarantine           = |market_divergence_pp| >= 15.
  plus `competition` (the stream code: INTL v0 rule 4 calls UNL only) and `venue_flag` (neutral_v3: home / neutral /
  unknown; INTL v0 rule 3).
- The document is sport "intl", so the Desk reads POLICY["INTL"] (desk_policy.py). Desk blocks are attached the
  way every export attaches them (desk_policy.maybe_annotate).
- Nothing is written to the database (the shadow writes none either). Whether a production intl row should also
  persist a Prediction is not in the ruling and is left open.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

EID = "intl-elo-v2"
SPORT = "intl"
ENGINE = "model_edge"
FILE_PREFIX = "intl_predictions_"
QUARANTINE_PP = 15.0          # the NFL contract (nfl_predict.py: abs(divergence_pp) >= 15.0)
VENUE_FLAG = {True: "neutral", False: "home", None: "unknown"}


class IntlRefused(RuntimeError):
    pass


def allowed() -> tuple[bool, str]:
    from src.walters import registry as reg
    return reg.production_allowed(EID)


def divergence_pp(p_home: float, market: dict | None):
    """The NFL definition: model HOME p minus the 1X2 book fair HOME, in pp (1 dp); None when unpriced."""
    m = market or {}
    if m.get("fair_source") != "1X2":
        return None
    fair = (m.get("fair_prob") or {}).get("HOME")
    return None if fair is None else round((p_home - fair) * 100, 1)


def production_row(shadow_row: dict, competition: str) -> dict:
    """A shadow row (intl_shadow.build_rows) re-shaped for the Desk. Pure."""
    sp = shadow_row["prediction"]
    row = {k: v for k, v in shadow_row.items() if k not in ("engine", "gate_verdict", "prediction")}
    div = divergence_pp(sp["home_win_prob"], row.get("market"))
    row.update({
        "competition": competition,
        "engine": ENGINE,
        "prediction": {
            "model_version": shadow_row.get("model_version"),
            "probabilities": {"home_win": sp["home_win_prob"], "draw": sp["draw_prob"],
                              "away_win": sp["away_win_prob"]},
            "top_pick": sp["top_pick"], "top_pick_prob": sp["top_pick_prob"],
            "tier": None,                     # no intl tier rule is declared; the Desk does not need one
            "elo_home": sp.get("elo_home"), "elo_away": sp.get("elo_away"),
            "home_adv_applied": sp.get("home_adv_applied"), "neutral_v3": sp.get("neutral_v3"),
        },
        "venue_flag": VENUE_FLAG[sp.get("neutral_v3")],
        "market_divergence_pp": div,
        "quarantine": div is not None and abs(div) >= QUARANTINE_PP,
    })
    row.pop("model_version", None)
    return row


def build(now: datetime | None = None, hours: int | None = None) -> dict:
    ok, why = allowed()
    if not ok:
        raise IntlRefused(f"{EID} is not production-allowed ({why}); export-unl-predictions stays the shadow")
    from src.db.database import session_scope
    from src.db.schema import Match
    from src.walters import intl_shadow as us

    r = us.build_rows(now, hours or us.WINDOW_HOURS)
    with session_scope() as s:
        codes = {}
        for x in r["rows"]:
            m = s.get(Match, x["match_id"])
            codes[x["match_id"]] = m.competition.code if m is not None and m.competition else None
        s.rollback()
    rows = [production_row(x, codes[x["match_id"]]) for x in r["rows"]]
    return {"rows": rows, "fit": r["fit"], "now": r["now"], "why": why}


def export(now: datetime | None = None, hours: int | None = None, out_dir: str = "exports",
           desk: bool | None = None) -> tuple[str, dict]:
    from src.walters import desk_policy as dp

    b = build(now, hours)
    now = b["now"]
    doc = {"sport": SPORT, "engine": ENGINE, "model_version": "intl_elo_v2", "production_allowed": b["why"],
           "exported_at": now.isoformat(), "count": len(b["rows"]), "fit": b["fit"], "predictions": b["rows"]}
    dp.maybe_annotate(doc, desk)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    path = str(Path(out_dir) / f"{FILE_PREFIX}{now.strftime('%Y-%m-%d_%H%M')}.json")
    with open(path, "w") as f:
        json.dump(doc, f, indent=2, default=str)
    return path, doc
