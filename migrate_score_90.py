"""
Migration (2026-09-26): matches.home_score_90 / away_score_90 — soccer's
90-minute score (API-Football score.fulltime, stored verbatim).

Adds to matches:
  - home_score_90  INTEGER   (NULL until the next sync touches the row)
  - away_score_90  INTEGER

Why: home/away_score are API-Football `goals`, which INCLUDE extra time
(pens excluded), so knockout ties level at 90' and decided in ET read as
wins against a 90-minute 1X2 price (the fix-v2 ET label-contamination
finding; architect data item 2026-09-25). The ET flag itself is
matches.status_raw in (AET, PEN) — stored by the same sync (no new column).
Storage only: no label, model or export reads these columns. Additive
and idempotent: safe to run repeatedly; never deletes or rewrites.

RUN ORDER: take the daily .backup first (law 5), then run this BEFORE any
chain after merging — the ORM now maps the columns, so queries on `matches`
fail with "no such column" until they exist. Requires migrate_status_raw.py
(already run for the NHL item).

Receipt: soccer FINISHED rows by status_raw, plus the 90-minute INVARIANTS
that verify the provider's semantics against our reading (law 1; revised
2026-09-26 after the first run BREACHED on two-legged ties):
  * FT rows' 90-minute score must EQUAL the stored score.
  * AET / PEN rows: 90' <= stored per side (ET can only add goals).
  * AET / PEN SINGLE-match ties (stage-based) must also be LEVEL at 90'.
Breaching rows print verbatim, with the stage classification table.
Right after migrating everything is NULL; populated going forward by the
normal syncs (a re-sync of a competition backfills it, e.g.
`python cli.py sync-matches --competition CL --seasons 2`).

Usage:
    python migrate_score_90.py
"""
from __future__ import annotations

import sys

from sqlalchemy import inspect, text

from src.db.database import get_engine

NEW_COLS = ("home_score_90", "away_score_90")


def main() -> int:
    engine = get_engine()
    inspector = inspect(engine)
    if "matches" not in inspector.get_table_names():
        print("✗ matches table doesn't exist — nothing to migrate.")
        return 1

    cols = {c["name"] for c in inspector.get_columns("matches")}
    if "status_raw" not in cols:
        print("✗ matches.status_raw missing — run migrate_status_raw.py first.")
        return 1
    with engine.begin() as conn:
        for col in NEW_COLS:
            if col in cols:
                print(f"· matches.{col} already exists.")
            else:
                print(f"+ Adding matches.{col}...")
                conn.execute(text(f"ALTER TABLE matches ADD COLUMN {col} INTEGER"))

    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT m.id, c.code, m.season, m.stage, m.utc_date, m.competition_id, "
            "  m.home_team_id, m.away_team_id, th.name, ta.name, "
            "  COALESCE(m.status_raw, '(null)'), m.home_score, m.away_score, "
            "  m.home_score_90, m.away_score_90 "
            "FROM matches m "
            "LEFT JOIN competitions c ON c.id = m.competition_id "
            "LEFT JOIN teams th ON th.id = m.home_team_id "
            "LEFT JOIN teams ta ON ta.id = m.away_team_id "
            "WHERE m.sport = 'SOCCER' AND m.status = 'FINISHED' "
            "ORDER BY m.utc_date, m.id"
        )).all()
    return report(rows)


# --------------------------------------------------------------------------
# Receipt + invariants (revised 2026-09-26, architect: the first run's
# BREACHED came from TWO-LEGGED ties, where ET triggers on AGGREGATE level,
# so a second leg need not be level at 90').
#   FT                      : 90' == stored score            (mandatory)
#   AET/PEN, every row      : 90' <= stored, per side         (ET only adds goals)
#   AET/PEN, SINGLE-match   : additionally level at 90'
# Single vs two-legged is STAGE-based; the classification is printed as a
# vocabulary table so it can be adjudicated, and unknown stages stay
# UNCLASSIFIED (universal check only) — never guessed into the strict law.
# --------------------------------------------------------------------------

# Every round is one match (domestic knockout cups, tournaments).
_SINGLE_MATCH_COMPS = {"FAC", "CS", "WC", "UEFA_EURO"}
# Two-legged apart from the listed single-match stages.
_UEFA_CLUB_COMPS = {"CL", "UEL", "EL", "UECL"}


def classify_stage(code: str | None, stage: str | None) -> str:
    """'single' | 'two-legged' | 'unclassified' for an AET/PEN row."""
    st = (stage or "").strip().lower()
    if not st:
        return "unclassified"
    if code in _SINGLE_MATCH_COMPS:
        return "single"
    if st in ("final", "3rd place final"):
        return "single"
    if code == "EFL":                                   # only the semis are two-legged
        return "two-legged" if st.startswith("semi") else "single"
    if code in _UEFA_CLUB_COMPS:
        return "single" if st.startswith("preliminary") else "two-legged"
    if code == "UNL":                                   # finals four single; QF/playoffs legged
        return "single" if st.startswith("semi") else "two-legged"
    return "unclassified"


def report(rows) -> int:
    """Print the receipt from (id, code, season, stage, utc, comp_id, home_id,
    away_id, home, away, raw, hs, as, h90, a90) rows. Always returns 0."""
    # print(), not rich: pasteable receipt lines
    by_raw: dict[str, list[int]] = {}
    for r in rows:
        c = by_raw.setdefault(r[10], [0, 0])
        c[0] += 1
        c[1] += r[13] is not None and r[14] is not None
    print("\nSoccer FINISHED rows by status_raw (receipt):")
    print(f"  {'raw':<8} {'rows':>7} {'with_90':>8}")
    if not rows:
        print("  (no soccer finished rows)")
    for raw in sorted(by_raw):
        print(f"  {raw:<8} {by_raw[raw][0]:>7} {by_raw[raw][1]:>8}")

    # reverse fixtures (same comp+season, home/away swapped, earlier) = leg-1 evidence
    seen = {(r[5], r[2], r[6], r[7]): r[4] for r in rows}

    def has_leg1(r):
        d = seen.get((r[5], r[2], r[7], r[6]))
        return d is not None and d < r[4]

    vocab: dict[tuple, int] = {}
    breaches: list[tuple[str, tuple]] = []
    for r in rows:
        raw, hs, as_, h90, a90 = r[10], r[11], r[12], r[13], r[14]
        if h90 is None or a90 is None:
            continue
        if raw == "FT":
            if (h90, a90) != (hs, as_):
                breaches.append(("FT 90'!=score", r))
            continue
        if raw not in ("AET", "PEN"):
            continue
        cls = classify_stage(r[1], r[3])
        vocab[(r[1], r[3], cls)] = vocab.get((r[1], r[3], cls), 0) + 1
        if hs is None or as_ is None or h90 > hs or a90 > as_:
            breaches.append((f"{raw} 90'>stored", r))
        elif cls == "single" and h90 != a90:
            breaches.append((f"{raw} single not level", r))

    print("\nAET/PEN stage classification (vocabulary receipt — adjudicate here):")
    if not vocab:
        print("  (no AET/PEN rows with a 90' score yet)")
    for (code, stage, cls), n in sorted(vocab.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        print(f"  {str(code):<6} {str(stage):<32} {cls:<13} {n:>5}")

    print("\nBreaching rows (verbatim; leg1 = reverse fixture earlier in comp+season):")
    if not breaches:
        print("  (none)")
    for why, r in breaches:
        print(f"  [{why}] #{r[0]} {r[1]} {r[2]} | {r[3]} | {r[4]} | {r[8]} v {r[9]} | "
              f"{r[10]} stored {r[11]}-{r[12]} | fulltime {r[13]}-{r[14]} | "
              f"class {classify_stage(r[1], r[3]) if r[10] != 'FT' else '-'} | "
              f"leg1 {'Y' if has_leg1(r) else 'n'}")

    kinds: dict[str, int] = {}
    for why, _ in breaches:
        kinds[why] = kinds.get(why, 0) + 1
    print("\nInvariants (revised: FT 90'==score; AET/PEN 90'<=stored per side; "
          "single-match AET/PEN level at 90'): "
          + ("HOLD" if not breaches else
             "BREACHED — " + "; ".join(f"{k}: {v}" for k, v in sorted(kinds.items()))))
    print("with_90 = 0 everywhere = not re-synced yet (populates going forward).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
