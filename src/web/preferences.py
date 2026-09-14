"""
User preferences persistence.

Simple JSON file at data/preferences.json. Single-user local app, so we don't
need user accounts or sessions — preferences are global to whoever runs the app.

Schema:
{
    "pinned_team_ids": [1, 47, ...],
    "default_league_code": "PL"
}

The selected_league for the current view comes from a cookie (per browser),
not from this file. This file is for things meant to persist across browsers /
machines if you ever copy the data dir.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from config import settings

log = logging.getLogger(__name__)

_PREFS_PATH = settings.project_root / "data" / "preferences.json"

# What goes in a fresh preferences file when the app first runs.
# Arsenal is the default pinned club per project requirements.
_DEFAULT_PREFS: dict[str, Any] = {
    "pinned_team_ids": [],
    "default_league_code": "PL",
    "focus_team_name": "Arsenal",  # used to auto-pin Arsenal on first load
}


def _load_raw() -> dict[str, Any]:
    if not _PREFS_PATH.exists():
        return dict(_DEFAULT_PREFS)
    try:
        with _PREFS_PATH.open() as f:
            data = json.load(f)
        # Backfill missing keys so older saves don't crash newer code
        for k, v in _DEFAULT_PREFS.items():
            data.setdefault(k, v)
        return data
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Could not read preferences (%s); using defaults.", e)
        return dict(_DEFAULT_PREFS)


def _save_raw(data: dict[str, Any]) -> None:
    _PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _PREFS_PATH.with_suffix(".tmp")
    with tmp.open("w") as f:
        json.dump(data, f, indent=2)
    tmp.replace(_PREFS_PATH)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_pinned_team_ids() -> list[int]:
    """Return the list of pinned team IDs."""
    return list(_load_raw().get("pinned_team_ids", []))


def pin_team(team_id: int) -> list[int]:
    data = _load_raw()
    pinned = list(data.get("pinned_team_ids", []))
    if team_id not in pinned:
        pinned.append(team_id)
        data["pinned_team_ids"] = pinned
        _save_raw(data)
    return pinned


def unpin_team(team_id: int) -> list[int]:
    data = _load_raw()
    pinned = [t for t in data.get("pinned_team_ids", []) if t != team_id]
    data["pinned_team_ids"] = pinned
    _save_raw(data)
    return pinned


def get_default_league() -> str:
    return _load_raw().get("default_league_code", "PL")


def set_default_league(code: str) -> None:
    data = _load_raw()
    data["default_league_code"] = code
    _save_raw(data)


def get_focus_team_name() -> str:
    return _load_raw().get("focus_team_name", "Arsenal")
