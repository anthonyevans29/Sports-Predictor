"""
THE DAY'S UNIT (ARCHITECT 2026-10-30 09:30 ET, addendum 179 items 3-5, #732; Desk policy v1.2).

Item 3, verbatim: "the day's unit is computed at the day's FIRST Desk page on the host (the first slate stage of the ET
day) as floor(UNIT_FRACTION × pool) in whole dollars, written to a small state file under logs/ (never data/) keyed by
the ET date, and every later page that day — slates and closings of every family — reads that file; the unit never
changes inside a day and never from a bet's own result."
Item 4, verbatim: "the floor is SP_UNIT_FLOOR_USD, set by hand in host.env and the laptop's .env (value never in the
repo; blocks check the name only), with the one requirement that a half-unit buys at least one contract at any price. A
balance read that fails leaves the day's unit UNREAD: the page carries no order line and says "unit unread — no order"
(law 4); a PLAY with no order line is not placed; the previous day's cached unit is NOT reused silently."

THE FILE: <dir>/desk_unit_<ET date>.json, dir = SP_DESK_UNIT_DIR, else the checkout's logs/ (gitignored, never
mirrored: exports_mirror pushes exports/ only). A dir with a `data` segment is refused (law 5). Written ONCE per ET day
(a temporary name beside it, then os.link, which refuses an existing name: closing.place_file's create-once), so a
second read that day, a retried slate or a second machine process finds the first and never re-reads the pool.
ARCHITECT 2026-10-30 10:15 ET, addendum 180 item 4, verbatim: "the unit file for the ET date is written by the FIRST
page that day whose read succeeds; a page that finds no file for its ET date makes the read itself and writes the file
on success; a page that finds the file never rewrites it (fixed for the day stands). So a failed read at the first page
costs that page its order line, not the day's. A page whose own read fails and finds no file says "unit unread — no
order"." So a failed read writes NOTHING: that page is unread, and the next page that day reads again. A day with no
file is unread (absent): yesterday's file is never read for today. Item 5: "an empty field-name constant, a missing
key, a non-numeric value, or a pool of zero each yield UNREAD, never a zero unit and never the floor; the floor applies
only to a unit computed from a successful read. The ET date is the page's time in America/New_York, not the host's UTC
day."

THE NUMBERS: unit = floor(UNIT_FRACTION x pool) in whole dollars, then the floor: max(that, floor) (#732 judgement J3:
the floor is the least a unit is). The half-unit requirement (item 4) is checked on the floor and on the unit: half of
it (HALF_UNIT_FRACTION / UNIT_FRACTION of a unit) must buy one contract at MAX_LIMIT, the highest limit an order line
writes. A floor that is set but is not a positive whole number, or that fails the requirement, leaves the day unread
(law 4). An unset floor applies no floor and says so; the requirement still holds on the unit.

The file holds the day's dollar unit (item 3: the state file) on every machine; the pool's dollar value only when the
caller's role is laptop (item 5: "the pages (the private mirror) and the laptop's logs only"), else pool_usd is null.
Nothing here prints them. `cli.py desk-unit` prints them on the laptop only.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from decimal import ROUND_FLOOR, Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from src.walters import desk_policy as dp

KIND = "desk_unit_v1"
DIR_ENV = "SP_DESK_UNIT_DIR"
DEFAULT_DIR = Path(__file__).resolve().parents[2] / "logs"
ET = ZoneInfo("America/New_York")
MAX_LIMIT = Decimal("0.99")          # the highest limit order_line writes: a cent price inside (0, 1)
HALF_OF_UNIT = Decimal(str(dp.HALF_UNIT_FRACTION)) / Decimal(str(dp.UNIT_FRACTION))     # 0.5: the half-unit


class UnitPathRefused(RuntimeError):
    """Law 5: the unit file never lands under a data/ folder."""


def et_date(now: datetime) -> date:
    """The ET day of `now` (a naive datetime is UTC, as the Desk reads kickoffs)."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(ET).date()


def unit_dir() -> Path:
    raw = (os.environ.get(DIR_ENV) or "").strip()
    d = Path(raw) if raw else DEFAULT_DIR
    refuse_data(d)
    return d


def refuse_data(p: Path) -> None:
    """Any path with a `data` segment is refused (law 5), before anything is read or written."""
    for q in (Path(p), Path(p).resolve()):
        if "data" in q.parts:
            raise UnitPathRefused(f"REFUSED: {q} has a data/ segment (law 5): the unit file never goes under data/")


def path_for(day: date) -> Path:
    return unit_dir() / f"desk_unit_{day.isoformat()}.json"


def read_day(day: date) -> dict | None:
    """The day's record: None when the day has no file (absent); a file that cannot be read, is not a desk_unit_v1
    record, or names another day reads as unread (law 4), never as a unit."""
    p = path_for(day)
    try:
        raw = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as e:
        return {"kind": KIND, "et_date": day.isoformat(), "state": "unread",
                "why": f"unit file unreadable ({e.__class__.__name__})"}
    try:
        rec = json.loads(raw)
    except ValueError:
        return {"kind": KIND, "et_date": day.isoformat(), "state": "unread", "why": "unit file is not JSON"}
    if not isinstance(rec, dict) or rec.get("kind") != KIND or rec.get("et_date") != day.isoformat():
        return {"kind": KIND, "et_date": day.isoformat(), "state": "unread",
                "why": "unit file is not this day's desk_unit_v1 record"}
    if rec.get("state") == "read" and not (isinstance(rec.get("unit_usd"), int) and rec["unit_usd"] > 0):
        return {"kind": KIND, "et_date": day.isoformat(), "state": "unread", "why": "unit file carries no unit"}
    return rec


def setting_reading(name: str) -> tuple[str | None, str]:
    """(value, source) of a hand-set name: the process environment, then the machine's host.env (SP_HOST_ENV, else
    desk_policy.HOST_ENV_DEFAULT), then the checkout's .env (desk_policy.DOTENV); (None, "unset") when none holds it,
    (None, "unreadable") when host.env exists and cannot be read (law 4: nothing after it is read)."""
    v = os.environ.get(name)
    if v is not None and v.strip():
        return v.strip(), "environment"
    got = _host_env()
    if got is None:
        return None, "unreadable"
    if (got.get(name) or "").strip():
        return got[name].strip(), "host.env"
    got = dp._env_file(dp.DOTENV)
    if (got.get(name) or "").strip():
        return got[name].strip(), ".env"
    return None, "unset"


def _host_env() -> dict | None:
    """The machine's host.env (SP_HOST_ENV, else desk_policy.HOST_ENV_DEFAULT): {} when it does not exist (the laptop),
    None when it exists and cannot be read."""
    got = dp._env_file(os.environ.get("SP_HOST_ENV", dp.HOST_ENV_DEFAULT), strict=True)
    return got if isinstance(got, dict) else None


def figures_allowed() -> bool:
    """Item 5: the pool and the unit in dollars print on the laptop's console only. True only when the machine's role
    reads exactly laptop, in the Desk's order (host.env, then the environment, then the checkout's .env, the first
    non-empty value deciding); a host.env that cannot be read, an unset role or any other value: no figure (law 4)."""
    name = dp.ROLE_ENV
    host = _host_env()
    if host is None:
        return False
    for src in (host, os.environ, dp._env_file(dp.DOTENV)):
        v = (src.get(name) or "").strip()
        if v:
            return v == "laptop"
    return False


def _half_buys_one(unit: Decimal) -> bool:
    return unit * HALF_OF_UNIT >= MAX_LIMIT


def compute(pool_usd, floor_raw: str | None, floor_source: str = "unset") -> dict:
    """The day's numbers from a pool in dollars and the floor's raw setting: {state read, unit_usd, floor_state} or
    {state unread, why}. Pure."""
    name = dp.UNIT_FLOOR_ENV
    try:
        pool = Decimal(str(pool_usd))
    except (InvalidOperation, ValueError):
        return {"state": "unread", "why": "the pool is not a number"}
    if not pool.is_finite() or pool <= 0:
        return {"state": "unread", "why": "the pool is not positive"}
    raw = int((Decimal(str(dp.UNIT_FRACTION)) * pool).to_integral_value(rounding=ROUND_FLOOR))
    if floor_raw is None:
        if floor_source == "unreadable":
            return {"state": "unread", "why": f"{name}: host.env exists but cannot be read (law 4)"}
        floor, floor_state = None, f"{name} unset: no floor applied"
    else:
        try:
            floor = Decimal(floor_raw)
        except (InvalidOperation, ValueError):
            return {"state": "unread", "why": f"{name} is not a number (law 4)"}
        if not floor.is_finite() or floor <= 0 or floor != floor.to_integral_value():
            return {"state": "unread", "why": f"{name} is not a positive whole number of dollars (law 4)"}
        if not _half_buys_one(floor):
            return {"state": "unread", "why": f"{name} fails the requirement: half a unit at the floor cannot buy "
                                              f"one contract at {MAX_LIMIT}"}
        if int(floor) > raw:
            # the unit is then above UNIT_FRACTION of the pool, said by name and never by figure; whether a floor above
            # the fraction, or above the whole pool, may stand is the architect's (#732 judgement J3, no ceiling yet)
            floor_state = (f"{name} applied (the floor binds: the unit is above UNIT_FRACTION of the pool"
                           + ("; the floor is above the whole pool" if floor > pool else "") + ")")
        else:
            floor_state = f"{name} set (not binding)"
    unit = max(raw, int(floor)) if floor is not None else raw
    if unit < 1 or not _half_buys_one(Decimal(unit)):
        return {"state": "unread", "why": f"half a unit cannot buy one contract at {MAX_LIMIT}: no floor lifts it "
                                          f"({floor_state})"}
    return {"state": "read", "unit_usd": unit, "floor_state": floor_state}


def _write_once(p: Path, rec: dict) -> bool:
    """Create `p` holding `rec` unless it exists: True when this call created it. The temporary name is hidden and
    carries the pid, so two writers never share it and no reader takes it for a day's file."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        try:
            os.link(tmp, p)                   # refuses an existing name: the day's first record stands
        except FileExistsError:
            return False
        return True
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def day_unit(now: datetime | None = None, *, read_pool=None, role: str | None = None) -> tuple[dict, bool]:
    """(the day's record, created): the day's file when it has one (the pool is not read again: once a day);
    else the pool is read (kalshi_pool.read_pool, or `read_pool` in tests), the unit computed and the record written
    once. A failed read (or a read whose numbers leave the unit unread) writes nothing and returns this page's unread
    record: the next page that day reads again (addendum 180 item 4). `created` False when the file was already there
    (or another process wrote it first), or when nothing was written. `role`: "laptop" keeps the pool's dollar value in the file; any other role keeps it null (item 5)."""
    now = now or datetime.now(timezone.utc)
    day = et_date(now)
    p = path_for(day)
    have = read_day(day)
    if have is not None:
        return have, False
    if read_pool is None:
        from src.walters.kalshi_pool import read_pool
    got = read_pool()
    rec = {"kind": KIND, "et_date": day.isoformat(), "fraction": dp.UNIT_FRACTION,
           "half_fraction": dp.HALF_UNIT_FRACTION, "floor_name": dp.UNIT_FLOOR_ENV, "policy_version": dp.POLICY_VERSION,
           "read_at": (now if now.tzinfo else now.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).strftime(
               "%Y-%m-%dT%H:%M:%SZ"), "role": role, "pool_usd": None, "unit_usd": None, "floor_state": None,
           "why": None}
    if not got.get("ok"):
        rec.update(state="unread", why=got.get("why") or "the balance read failed")
        return rec, False             # addendum 180 item 4: this page is unread; nothing is written for the day
    else:
        if role == "laptop":      # item 5: the pool's dollar value goes in the laptop's logs only, never the host's
            rec["pool_usd"] = float(Decimal(str(got["pool_usd"])).quantize(Decimal("0.01")))
        floor_raw, src = setting_reading(dp.UNIT_FLOOR_ENV)
        num = compute(got["pool_usd"], floor_raw, src)
        rec.update(state=num["state"], unit_usd=num.get("unit_usd"), floor_state=num.get("floor_state"),
                   why=num.get("why"))
        if rec["state"] != "read":
            return rec, False         # no unit computed from this read: nothing written, the next page reads again
    try:
        created = _write_once(p, rec)
    except OSError as e:
        return {**rec, "state": "unread", "unit_usd": None,
                "why": f"unit file not written ({e.__class__.__name__}): the day stays unread"}, False
    if not created:
        return read_day(day) or {**rec, "state": "unread", "why": "unit file vanished"}, False
    return rec, True
