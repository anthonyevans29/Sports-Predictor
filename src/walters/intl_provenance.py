"""
UNL VENUE-INPUT PROVENANCE RECEIPT (ARCHITECT 2026-10-23, addendum 159 item 2; #336) — read-only.

Verbatim: "UNL, venue-input provenance (#336, ruling). Confirmation replays the frozen method on the stored results
and the stored neutral_v3 flags; shadow grading reads the pre-kickoff files. Both stand as built. Code: a read-only
receipt before 11-11 — the input snapshot the read uses (ids, results, neutral_v3 per cohort fixture, with each flag's
ingest time), the fixtures whose stored flag changed after their pre-kickoff shadow file was written, and the replayed
vs saved probability on those; missing shadow files listed as missing. Any material difference comes to me; nobody
picks the better set. #336's closing receipt is this."

And addendum 160 item 3, verbatim in part: "The read on 11-12 is reported BOTH ways (stored flags; corrected flags);
the verdict is taken on the corrected inputs; the frozen method is untouched. The provenance receipt of 159 item 2
lists exactly which cohort fixtures move".

Per cohort fixture (intl_shadow.cohort: frozen in the registry, else provisional), in cohort order:
  - the input snapshot: id, kickoff, competition, status, the 90-minute result as the stream reads it
    (intl_shadow.result_90; none while unplayed), the stored neutral_v3 and the flag's ingest time
    (intl_match_venue.derived_at), and the flag from the provider's venue country alone (intl_venues.provider_flag): a
    fixture whose two flags differ is one a keyed override moves (160 item 3);
  - the pre-kickoff shadow file (intl_shadow.last_calls: the last row written before kickoff), or MISSING;
  - CHANGED AFTER THE FILE: the stored flag differs from the one the file priced, or its ingest time is later than the
    file's export time. For those, the probability REPLAYED now (the frozen method: intl_elo.IntlElo at the run
    record's multipliers and the training mu, walked over the stored stream games kicking off before the file's export
    time, then the fixture priced with its stored flag) against the SAVED one, with the largest |diff|.
Nothing is chosen between the two sets: the receipt lists, the architect rules. One session, rolled back.
"""
from __future__ import annotations

from datetime import datetime

RULING = "ARCHITECT 2026-10-23, addendum 159 item 2 (#336)"
ROUNDING = 5e-5                    # the shadow file stores 4 decimals: a |diff| at or under this is rounding


def _flag(v) -> str:
    return "unknown" if v is None else "neutral" if v else "home"


def _parse(at: str | None) -> datetime | None:
    if not at:
        return None
    try:
        d = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.replace(tzinfo=None)


def receipt(export_dir: str = "exports") -> dict:
    from sqlalchemy import select

    from src.db.database import session_scope
    from src.db.schema import Competition, IntlMatchVenue, Match
    from src.ingestion.intl_venues import provider_flag
    from src.walters import intl_elo as ie
    from src.walters import intl_shadow as sh

    e, c_mult, k_mult = sh.frozen()
    with session_scope() as s:
        games, _ = ie.load(s, rule="v3")
        co = sh.cohort(e, s)
        ids = list(co["ids"])
        venue = {v.match_id: v for v in s.execute(select(IntlMatchVenue).where(IntlMatchVenue.match_id.in_(ids)))
                 .scalars()} if ids else {}
        fx = {m.id: (m, code) for m, code in s.execute(
            select(Match, Competition.code).join(Competition, Competition.id == Match.competition_id)
            .where(Match.id.in_(ids))).all()} if ids else {}
        snap = []
        for i in ids:
            m, code = fx.get(i, (None, None))
            v = venue.get(i)
            snap.append({"id": i, "stored": m is not None, "kickoff": m.utc_date if m else None, "code": code,
                         "season": m.season if m else None, "home": m.home_team_id if m else None,
                         "away": m.away_team_id if m else None,
                         "status": (m.status.value if hasattr(m.status, "value") else str(m.status)) if m else None,
                         "result": sh.result_90(m) if m else None, "venue_row": v is not None,
                         "flag": v.neutral_v3 if v else None, "flag_at": v.derived_at if v else None,
                         "provider_flag": provider_flag(v.venue_country, v.home_country) if v else None,
                         "venue_id": v.venue_id if v else None})
        s.rollback()
    train = [g for g in games if ie.TRAIN_FROM <= g.kickoff < ie.TRAIN_TO]
    mu = sum(g.hg + g.ag for g in train) / (2 * len(train)) if train else None
    calls = sh.last_calls(export_dir)
    for x in snap:
        c = calls.get(x["id"])
        x["file"] = c["source_file"] if c else None
        x["exported_at"] = _parse(c["exported_at"]) if c else None
        x["saved_flag"] = (c.get("prediction") or {}).get("neutral_v3") if c else None
        x["changed"] = bool(c) and (x["saved_flag"] != x["flag"]
                                    or (x["flag_at"] is not None and x["exported_at"] is not None
                                        and x["flag_at"] > x["exported_at"]))
        x["replay"] = None
        if x["changed"] and mu is not None and x["stored"] and x["exported_at"] is not None:
            m = ie.IntlElo(mu=mu, c_mult=c_mult, k_mult=k_mult)
            for g in games:
                if g.kickoff < x["exported_at"]:
                    m.update(g)
            g = ie.Game(x["id"], x["code"], x["season"], x["kickoff"], x["home"], x["away"], 0, 0, x["flag"])
            rp = m.probs(g)
            p = c.get("prediction") or {}
            sp = (p.get("home_win_prob"), p.get("draw_prob"), p.get("away_win_prob"))
            diff = max(abs(a - b) for a, b in zip(rp, sp)) if None not in sp else None
            x["replay"] = {"replayed": rp, "saved": sp, "diff": diff}
    changed = [x for x in snap if x["changed"]]
    diffs = [x["replay"]["diff"] for x in changed if x["replay"] and x["replay"]["diff"] is not None]
    return {"cohort_state": co["state"], "n_games": co["n_games"], "snapshot": snap, "mu": mu,
            "c_mult": c_mult, "k_mult": k_mult, "changed": changed,
            "material": sum(1 for d in diffs if d > ROUNDING), "max_diff": max(diffs, default=None),
            "missing": [x["id"] for x in snap if x["file"] is None],
            "moved_by_override": [x["id"] for x in snap if x["venue_row"] and x["flag"] != x["provider_flag"]]}


def lines(r: dict) -> list[str]:
    snap = r["snapshot"]
    L = [f"UNL VENUE-INPUT PROVENANCE ({RULING}) · read-only · cohort {r['cohort_state'].upper()} "
         f"({len(snap)} of {r['n_games']}) · labelled {sum(1 for x in snap if x['result'])} · with a venue row "
         f"{sum(1 for x in snap if x['venue_row'])} · pre-kickoff shadow file {len(snap) - len(r['missing'])} · "
         f"MISSING {len(r['missing'])}",
         f"  frozen method: IntlElo, mu {r['mu'] if r['mu'] is None else round(r['mu'], 4)}, c_mult {r['c_mult']}, "
         f"k_mult {r['k_mult']} (the run record's)",
         f"  moved by a venue-country override (stored flag != the provider's country alone; 160 item 3): "
         f"{len(r['moved_by_override'])}" + (f" — {', '.join(map(str, r['moved_by_override']))}"
                                              if r["moved_by_override"] else ""),
         "  THE INPUT SNAPSHOT (per cohort fixture: id · kickoff · competition · status · 90-minute result · stored "
         "neutral_v3 [provider's] · the flag's ingest time · pre-kickoff shadow file):"]
    for x in snap:
        if not x["stored"]:
            L.append(f"    - {x['id']} · NOT STORED on this machine")
            continue
        L.append(f"    - {x['id']} · {x['kickoff']:%Y-%m-%d %H:%M}Z · {x['code']} · {x['status']} · result "
                 f"{x['result'] or 'none'} · neutral_v3 {_flag(x['flag'])}"
                 + (f" [provider's {_flag(x['provider_flag'])}]" if x["provider_flag"] != x["flag"] else "")
                 + (f" · flag at {x['flag_at']:%Y-%m-%d %H:%M}Z" if x["flag_at"] else " · no venue row")
                 + (f" · file {x['file']}" if x["file"] else " · shadow file MISSING"))
    L.append(f"  CHANGED AFTER THE PRE-KICKOFF FILE: {len(r['changed'])} · replayed vs saved: material (|diff| > "
             f"{ROUNDING:g}, the file's rounding) {r['material']}"
             + (f" · max |diff| {r['max_diff']:.4f}" if r["max_diff"] is not None else ""))
    for x in r["changed"]:
        rp = x["replay"]
        L.append(f"    - {x['id']} · file {x['file']} (exported {x['exported_at']:%Y-%m-%d %H:%M}Z) priced "
                 f"neutral_v3 {_flag(x['saved_flag'])}; stored now {_flag(x['flag'])}"
                 + (f" (ingested {x['flag_at']:%Y-%m-%d %H:%M}Z)" if x["flag_at"] else "")
                 + (f" · replayed {'/'.join(f'{p:.4f}' for p in rp['replayed'])} vs saved "
                    f"{'/'.join(f'{p:.4f}' if p is not None else '—' for p in rp['saved'])}"
                    + (f" · |diff| {rp['diff']:.4f}" if rp["diff"] is not None else "") if rp else " · not replayed"))
    if r["material"]:
        L.append(f"  TO THE ARCHITECT: {r['material']} material difference(s) (159 item 2: \"Any material difference "
                 "comes to me; nobody picks the better set.\")")
    return L
