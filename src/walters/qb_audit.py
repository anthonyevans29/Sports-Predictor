"""
NFL QB-feed audit + the shared QB resolver (architect 2026-09-29).

Week 4 MNF: Chicago started its backup QB while the export said
qb_listed [] beside 6 stored Bears injury rows. qb_listed comes from
Injury.player_position == "QB", and the provider's /injuries carries NO
position (raw probe 2026-09-09): the adapter joins positions from the team
roster by provider player id. So an injured QB can vanish three ways:

  H1  the QB is not on the provider's injury report at all;
  H2  he is on it, but his position did not resolve (roster fetch failed or
      returned nothing, the id join missed, or a position spelled other than
      "QB");
  H3  he is on it with an old report date, and the service's 14-day
      fixture-date freshness filter (a soccer rule for fixture-history feeds)
      dropped him while he is still listed.

This module is the ONE place both the adapter (detection) and the
`nfl-qb-audit` command (the receipt) resolve positions, so the receipt
exercises the code that ships. Pure functions; the command does the I/O.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

QB_POSITIONS = {"QB", "QUARTERBACK"}
STALE_INJURY_DAYS = 14   # the service's filter, mirrored for the H3 read


def is_qb(position: str | None) -> bool:
    return (position or "").strip().upper() in QB_POSITIONS


def _norm(name: str) -> str:
    n = re.sub(r"[^a-z ]+", " ", (name or "").lower())
    return " ".join(w for w in n.split() if w not in {"jr", "sr", "ii", "iii", "iv"})


def _initial_key(name: str) -> str | None:
    parts = _norm(name).split()
    return f"{parts[0][0]} {parts[-1]}" if len(parts) >= 2 else None


def roster_index(roster: list[dict]) -> dict:
    """Provider roster rows -> lookups by id, full name, and initial+surname.

    ARCHITECT 2026-10-12, addendum 47 item 4 (#451): "A group is not a position. In the roster join, as in the lookup,
    only the position field resolves a player. A roster row without one leaves him unresolved, and where the lookup
    runs he is asked by id." Only `position` is read (never `group`).
    Addendum 47 item 3 (#454): "A name the roster holds more than once resolves nobody by name." Held more than once
    by this join's own comparison (_norm: "Michael Carter" and "Michael Carter II" are one name held twice), counted
    over every roster row, with a position or not. by_name and by_init are unique-only; never a guess."""
    by_id, by_name, by_init, name_count, init_count = {}, {}, {}, {}, {}
    for rp in roster or []:
        p = rp.get("player") if isinstance(rp.get("player"), dict) else rp
        nm = _norm(p.get("name") or "")
        k = _initial_key(p.get("name") or "")
        if nm:
            name_count[nm] = name_count.get(nm, 0) + 1
        if k:
            init_count[k] = init_count.get(k, 0) + 1
        pos = p.get("position")
        pos = pos.strip() if isinstance(pos, str) else pos
        if not pos:
            continue
        if p.get("id") is not None:
            by_id[p["id"]] = str(pos)
        if nm:
            by_name[nm] = str(pos)
        if k:
            by_init[k] = str(pos)
    return {"by_id": by_id,
            "by_name": {k: v for k, v in by_name.items() if name_count[k] == 1},
            "by_init": {k: v for k, v in by_init.items() if init_count[k] == 1},
            "size": len(roster or [])}


def resolve_position(player: dict, idx: dict, by_name: bool = True) -> tuple[str | None, str | None]:
    """(position, how): by provider id, then a UNIQUE exact name, then a UNIQUE initial+surname match. (None, None)
    stays None: unknown, never guessed. by_name=False: the id alone (addendum 47 item 3: entries that share a name
    and differ in id are "resolved by its own id, from the roster and then by the lookup, never by a name")."""
    pid, name = player.get("id"), player.get("name") or ""
    if pid is not None and pid in idx["by_id"]:
        return idx["by_id"][pid], "roster_id"
    if not by_name:
        return None, None
    if _norm(name) in idx["by_name"]:
        return idx["by_name"][_norm(name)], "roster_name"
    k = _initial_key(name)
    if k and k in idx["by_init"]:
        return idx["by_init"][k], "roster_initial"
    return None, None


def injury_entries(items: list[dict]) -> list[tuple[dict, bool]]:
    """THE ENTRIES OF THE INJURIES READ (ARCHITECT 2026-10-12, addendum 47 item 3, #454): "In the injuries read an
    entry is told apart by its provider id. One id listed more than once is one entry, the first. Entries that share
    a name and differ in id are different players: each is kept, and each is resolved by its own id, from the roster
    and then by the lookup, never by a name. An entry with no id is resolved by name as today, and is kept only where
    no other entry has its name." The ONE place the adapter's read and the audit (audit_live) take the entries.
    Returns [(item, by_name)]: by_name is False for an entry whose name another entry of the read has (names compared
    by _norm), id-less ones included (Codex on #456), so it is resolved by its own id alone. Entries with no name are
    skipped (no row to write)."""
    kept, seen_ids = [], set()
    for item in items or []:
        pl = item.get("player") or {}
        if not (pl.get("name") or "").strip():
            continue
        if pl.get("id") is not None:
            if str(pl["id"]) in seen_ids:
                continue                   # one id listed more than once: one entry, the first
            seen_ids.add(str(pl["id"]))
        kept.append(item)
    name_n: dict = {}
    for item in kept:
        nm = _norm(item["player"]["name"])
        name_n[nm] = name_n.get(nm, 0) + 1
    out = []
    for item in kept:
        shared = name_n[_norm(item["player"]["name"])] > 1
        if item["player"].get("id") is None and shared:
            continue                       # no id, and another entry has its name: not kept
        out.append((item, not shared))
    return out


def _old_filter_drops(date_str: str | None, now: datetime) -> bool:
    if not date_str:
        return False
    try:
        d = datetime.fromisoformat(str(date_str).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return False
    return d < now - timedelta(days=STALE_INJURY_DAYS)


def audit_live(injuries: list[dict], roster: list[dict], now: datetime,
               old_id_only: bool = True) -> dict:
    """Classify the provider's raw /injuries items against its roster.
    Returns per-item rows and the H1/H2/H3 verdict lines."""
    idx = roster_index(roster)
    roster_qbs = sorted({(rp.get("player") if isinstance(rp.get("player"), dict) else rp).get("name")
                         for rp in roster or []
                         if is_qb((rp.get("player") if isinstance(rp.get("player"), dict) else rp).get("position"))})
    items = []
    for it, by_name in injury_entries(injuries):         # the read's own entries (addendum 47 item 3)
        pl = it.get("player") or {}
        pos, how = resolve_position(pl, idx, by_name=by_name)
        old_pos = idx["by_id"].get(pl.get("id"))          # the pre-fix join: id only
        items.append({"name": pl.get("name"), "id": pl.get("id"), "status": it.get("status"),
                      "date": it.get("date"), "position": pos, "resolved_by": how,
                      "old_position": old_pos, "old_qb": (old_pos or "").upper() == "QB",
                      "qb": is_qb(pos), "old_filter_drops": _old_filter_drops(it.get("date"), now)})
    verdict = []
    qbs = [i for i in items if i["qb"]]
    if idx["size"] == 0:
        verdict.append("H2: roster came back EMPTY — every injured player's position is None, qb_listed [] is blind")
    if not qbs:
        on_report = {_norm(i["name"] or "") for i in items}
        verdict.append("H1: no QB on the provider's injury report"
                       + (f" (roster QBs: {', '.join(n for n in roster_qbs if n)}; none of them listed)"
                          if roster_qbs else "")
                       if not any(_norm(n or "") in on_report for n in roster_qbs) else
                       "H2: a roster QB is on the report but his position did not resolve")
    for q in qbs:
        why = []
        if not q["old_qb"]:
            why.append(f"H2: the pre-fix id-only join missed him (resolved by {q['resolved_by']}, "
                       f"old position {q['old_position']!r})")
        if q["old_filter_drops"]:
            why.append(f"H3: report date {q['date']} is > {STALE_INJURY_DAYS} days old — the 14-day "
                       f"filter dropped him while the provider still lists him ({q['status']})")
        verdict.append(f"{q['name']} ({q['status']}): " + ("; ".join(why) if why else
                       "resolved and kept by the pre-fix code too — look at sync timing (stored rows)"))
    return {"items": items, "roster_size": idx["size"], "roster_qbs": roster_qbs, "verdict": verdict}


def audit_stored(rows: list, kickoff: datetime | None) -> dict:
    """What the DB held: the stored Injury rows for the team, the pre-fix
    and fixed QB reads, unresolved positions, and sync timing vs kickoff."""
    stamp = max((r.refreshed_at for r in rows), default=None)
    return {"count": len(rows),
            "rows": [{"name": r.player_name, "position": r.player_position, "status": r.type,
                      "reason": r.reason, "refreshed_at": r.refreshed_at} for r in rows],
            "qb_old": [r.player_name for r in rows if (r.player_position or "").upper() == "QB"],
            "qb_fixed": [r.player_name for r in rows if is_qb(r.player_position)],
            "unresolved": [r.player_name for r in rows if not r.player_position],
            "synced_at": stamp,
            "synced_before_kickoff_h": (round((kickoff - stamp).total_seconds() / 3600, 1)
                                        if stamp and kickoff else None)}
