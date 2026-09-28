"""Export provenance (parallel-week exhibit 1 ruling, 2026-09-28).

Every JSON export carries the producing checkout's git SHA (`git_sha`), so the
parallel-week comparator can class a divergence as CODE-VERSION SKEW only when
both files name their SHAs and they differ (exhibit 1: the laptop's 17-row NFL
file was pre-#53, the host's 1-row file post-#53). Unknown stays null and
labelled — never guessed (law 4).
"""
from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def git_sha() -> str | None:
    """Short SHA of the producing checkout (SP_GIT_SHA overrides), else None."""
    env = os.environ.get("SP_GIT_SHA")
    if env:
        return env.strip() or None
    try:
        out = subprocess.run(["git", "-C", str(_REPO), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None
