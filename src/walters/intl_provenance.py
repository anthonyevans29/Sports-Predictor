"""UNL VENUE-INPUT PROVENANCE RECEIPT (ARCHITECT 2026-10-23, addendum 159 item 2; #336), rebuilt from #336 on current
main (ARCHITECT 2026-11-19, addenda 426 item 5(b) and 429 item 1(c); the 10-23 branch claude/159-unl-provenance a
reference, never merged as it stands, 287 item 3(B)).

159 item 2, verbatim: "Confirmation replays the frozen method on the stored results and the stored neutral_v3 flags;
shadow grading reads the pre-kickoff files. Both stand as built. Code: a read-only receipt before 11-11 — the input
snapshot the read uses (ids, results, neutral_v3 per cohort fixture, with each flag's ingest time), the fixtures whose
stored flag changed after their pre-kickoff shadow file was written, and the replayed vs saved probability on those;
missing shadow files listed as missing. Any material difference comes to me; nobody picks the better set. #336's
closing receipt is this."

429 item 1(c): "THE PROVENANCE RECEIPT RUNS ON THE LAPTOP, by my block, on the pulled copy. Its shadow files are in two
places [...] So --export-dir is given more than once, each a flat directory or a tree of dated folders, never latest/
(232 item 2(c)'s reading). A missing file is listed as missing (159 item 2)."

Read-only: one session (the copy's mode=ro + immutable=1 session under addendum 346's fence, or the app's database
mode=ro); nothing written, nothing fetched. The frozen method is intl_shadow's: c_mult and k_mult from the registry's
run record (frozen()), mu the training goals' mean, the walk predict-then-update over the stored stream (rule v3).
"Material": a replayed probability differs from the saved one by more than ROUNDING, half a unit of the shadow file's
fourth decimal.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

RULING = "ARCHITECT 2026-10-23, addendum 159 item 2 (#336); 429 item 1(c)"
ROUNDING = 5e-5


def _flag(v) -> str:
    return "unknown" if v is None else "neutral" if v else "home"


def _parse(at) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return d.replace(tzinfo=None) if d.tzinfo else d      # the files and the store are naive UTC


def shadow_files(export_dirs) -> tuple[list[Path], list[str]]:
    """The unl_shadow files of every --export-dir and its dated folders (early_arm._dirs: <dir> and each <YYYY-MM-DD>/;
    latest/ refused, given directly or behind a dated-named folder), each file once (by its resolved path), in a fixed
    order. (files, the folders read). A --export-dir that is not a directory is refused."""
    from src.walters import early_arm as ea
    from src.walters import intl_shadow as sh

    if not export_dirs:
        raise sh.ShadowRefused("give --export-dir at least once (429 item 1(c)); nothing read")
    files, seen, folders = [], set(), []
    for d in export_dirs:
        if not Path(d).is_dir():
            raise sh.ShadowRefused(f"--export-dir {d}: not a directory; nothing read")
        try:
            dirs = ea._dirs(d)
        except ea.LatestRefused as e:                    # early_arm names its own flag; this command's is --export-dir
            raise sh.ShadowRefused(str(e).replace("--exports ", "--export-dir ", 1)) from None
        for sub in dirs:
            folders.append(str(sub))
            for f in sorted(sub.glob(f"{sh.FILE_PREFIX}*.json")):
                key = f.resolve()
                if key not in seen:
                    seen.add(key)
                    files.append(f)
    return files, folders


def receipt(s, export_dirs) -> dict:
    """The receipt's content, read through the session `s` (nothing written)."""
    from sqlalchemy import select

    from src.db.schema import Competition, IntlMatchVenue, Match
    from src.ingestion import intl_venues as iv
    from src.walters import intl_elo as ie
    from src.walters import intl_shadow as sh

    files, folders = shadow_files(export_dirs)
    e, c_mult, k_mult = sh.frozen()
    games, _ = ie.load(s, rule="v3")
    co = sh.cohort(e, s)
    ids = list(co["ids"])
    venue = {v.match_id: v for v in s.execute(select(IntlMatchVenue).where(IntlMatchVenue.match_id.in_(ids)))
             .scalars()}
    stored = {m.id: (m, code) for m, code in s.execute(
        select(Match, Competition.code).join(Competition, Competition.id == Match.competition_id)
        .where(Match.id.in_(ids))).all()}
    train = [g for g in games if ie.TRAIN_FROM <= g.kickoff < ie.TRAIN_TO]
    mu = sum(g.hg + g.ag for g in train) / (2 * len(train)) if train else None
    calls = sh.calls_from_files(files, label=lambda f: str(f))

    snapshot, changed, missing, moved = [], [], [], []
    for mid in ids:
        mv = stored.get(mid)
        v = venue.get(mid)
        c = calls.get(mid)
        row = {"id": mid, "stored": mv is not None, "venue_row": v is not None,
               "flag": v.neutral_v3 if v else None, "flag_at": v.derived_at if v else None,
               "provider_flag": iv.provider_flag(v.venue_country, v.home_country) if v else None,
               "venue_id": v.venue_id if v else None, "file": c["source_file"] if c else None,
               "exported_at": _parse(c["exported_at"]) if c else None,
               "saved_flag": (c.get("prediction") or {}).get("neutral_v3") if c else None}
        if mv is not None:
            m, code = mv
            row.update({"kickoff": m.utc_date, "code": code, "season": m.season,
                        "status": getattr(m.status, "value", m.status), "result": sh.result_90(m),
                        "home": m.home_team_id, "away": m.away_team_id})
        snapshot.append(row)
        if c is None:
            missing.append(mid)
        if v is not None and row["flag"] != row["provider_flag"]:
            moved.append(mid)
        if c is not None and mv is not None and (
                row["saved_flag"] != row["flag"]
                or (row["flag_at"] and row["exported_at"] and row["flag_at"] > row["exported_at"])):
            changed.append(row)
    for row in changed:
        p = c_saved = None
        if mu is not None and row["exported_at"] is not None:
            model = ie.IntlElo(mu=mu, c_mult=c_mult, k_mult=k_mult)
            for g in games:
                if g.kickoff >= row["exported_at"]:
                    break
                model.update(g)
            p = model.probs(ie.Game(row["id"], row["code"], row["season"], row["kickoff"], row["home"], row["away"],
                                    0, 0, row["flag"]))
            pr = calls[row["id"]].get("prediction") or {}
            c_saved = tuple(pr.get(k) for k in ("home_win_prob", "draw_prob", "away_win_prob"))
        row["replayed"] = p
        row["saved"] = c_saved
        row["diff"] = (max(abs(a - float(b)) for a, b in zip(p, c_saved))
                       if p is not None and c_saved and None not in c_saved else None)
    material = [r for r in changed if r["diff"] is not None and r["diff"] > ROUNDING]
    return {"cohort_state": co["state"], "n_games": co["n_games"], "n_cohort": len(ids), "snapshot": snapshot,
            "mu": mu, "c_mult": c_mult, "k_mult": k_mult, "changed": changed, "material": material,
            "max_diff": max((r["diff"] for r in changed if r["diff"] is not None), default=None),
            "missing": missing, "moved_by_override": moved, "files": len(files), "folders": folders}


def lines(r: dict) -> list[str]:
    snap = r["snapshot"]
    labelled = sum(1 for x in snap if x.get("result"))
    with_row = sum(1 for x in snap if x["venue_row"])
    with_file = sum(1 for x in snap if x["file"])
    L = [f"UNL VENUE-INPUT PROVENANCE ({RULING}) · read-only · cohort {str(r['cohort_state']).upper()} "
         f"({r['n_cohort']} of {r['n_games']}) · labelled {labelled} · with a venue row {with_row} · pre-kickoff "
         f"shadow file {with_file} · MISSING {len(r['missing'])}",
         f"  shadow files read {r['files']} from {len(r['folders'])} folder(s): " + ", ".join(r["folders"]),
         "  the frozen method: mu " + (f"{r['mu']:.4f}" if r["mu"] is not None else "unknown (no training games)")
         + f" · c_mult {r['c_mult']} · k_mult {r['k_mult']} (the registry's run record; never refit)",
         f"  moved by a venue-country override (stored flag != the provider's country alone; 160 item 3): "
         f"{len(r['moved_by_override'])}" + (" — " + ", ".join(map(str, r["moved_by_override"]))
                                             if r["moved_by_override"] else ""),
         "  THE INPUT SNAPSHOT (the read's inputs, per cohort fixture):"]
    for x in snap:
        if not x["stored"]:
            L.append(f"    {x['id']} · NOT STORED on this store")
            continue
        flag = f"neutral_v3 {_flag(x['flag'])}" + (f" [provider's {_flag(x['provider_flag'])}]"
                                                     if x["venue_row"] and x["flag"] != x["provider_flag"] else "")
        L.append(f"    {x['id']} · {x['kickoff']:%Y-%m-%d %H:%M}Z · {x['code']} · {x['status']} · result "
                 f"{x['result'] or 'none'} · " + (f"{flag} · flag at {x['flag_at']:%Y-%m-%d %H:%M}Z"
                                                    if x["venue_row"] and x["flag_at"] else
                                                    flag if x["venue_row"] else "no venue row")
                 + f" · " + (f"file {x['file']}" if x["file"] else "shadow file MISSING"))
    mx = r["max_diff"]
    L.append(f"  CHANGED AFTER THE PRE-KICKOFF FILE: {len(r['changed'])} · replayed vs saved: material (|diff| > "
             f"{ROUNDING:g}) {len(r['material'])} · max |diff| " + (f"{mx:.6f}" if mx is not None else "none"))
    for x in r["changed"]:
        rp, sv = x.get("replayed"), x.get("saved")
        L.append(f"    {x['id']} · file {x['file']} · exported {x['exported_at']:%Y-%m-%d %H:%M}Z · priced "
                 f"{_flag(x['saved_flag'])} · stored now {_flag(x['flag'])}"
                 + (f" · ingested {x['flag_at']:%Y-%m-%d %H:%M}Z" if x["flag_at"] else "")
                 + (f" · replayed {rp[0]:.4f}/{rp[1]:.4f}/{rp[2]:.4f} vs saved {sv[0]}/{sv[1]}/{sv[2]} · |diff| "
                    f"{x['diff']:.6f}" if rp is not None and x["diff"] is not None else " · not replayed"))
    if r["missing"]:
        L.append(f"  MISSING shadow files ({len(r['missing'])}): " + ", ".join(map(str, r["missing"])))
    if r["material"]:
        L.append(f"  TO THE ARCHITECT: {len(r['material'])} material difference(s) (159 item 2: \"Any material "
                 "difference comes to me; nobody picks the better set.\")")
    return L
