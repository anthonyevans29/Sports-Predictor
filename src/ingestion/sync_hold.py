"""SP_SYNC_HOLD: a per-competition sync hold the step itself honors (ARCHITECT 2026-11-10 18:55 ET, addendum 332 item
3, verbatim): "THE DURABLE ANSWER is a per-competition sync hold the step itself honors: SP_SYNC_HOLD, a list of
competition codes read by sync-teams and sync-matches, which print "HELD <code> (SP_SYNC_HOLD)" and exit 0 for a listed
code, every chain and timer unchanged, the window and fullseason plans unchanged; a receipt line counts the held
steps." And (addendum 333 item 3(iii), verbatim): "the rule follows the WRITE PATH (_upsert_match), not the step's
name [...] SP_SYNC_HOLD (#921) honors the same path: its design covers intl-sync, or says in its body why not."

WHERE IT IS READ: on every check, from three places, and a code named in ANY of them is held (holding more is the
safe direction, law 4): the process environment; the host's env file (SP_HOST_ENV, default
/etc/sports-predictor/host.env, as sp_common reads it); and the checkout's .env (the laptop). Re-reading the files
on each check means a run by hand outside a unit (a closing-run, a bare sync) and a long-running process (the admin
UI's web server) see a hold set after they started, with no restart. Lifting a hold removes the code from every
place that names it; a process that inherited the code in its environment at start keeps holding it until it
restarts. Codes are separated by commas or blanks and read case-insensitively. Unset or empty everywhere holds
nothing. Honored by `sync-teams`, `sync-matches`
(every source: the MLB api-sports fallback and the tennis path included, checked before either), `refresh-by-id`
(NCAA, NFL: it writes kickoff, status and scores by id) and `intl-sync` (per code of its plan). A held step writes
nothing for that code and exits 0. sp_run counts the steps that printed the line (sp_run.HELD_LINE).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

ENV = "SP_SYNC_HOLD"
_SPLIT = re.compile(r"[,\s]+")


REPO = Path(__file__).resolve().parents[2]


def _parse(v: str | None) -> frozenset:
    return frozenset(x.upper() for x in _SPLIT.split((v or "").strip()) if x)


def _env_file(path: Path) -> str | None:
    """SP_SYNC_HOLD's value in a KEY=VALUE file (sp_common.parse_env_file's rules: '#' comments, `export `, quotes
    stripped); None when the file or the key is absent or unreadable."""
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError):
        return None
    v = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, val = line.split("=", 1)
        if k.strip().removeprefix("export ").strip() == ENV:
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            v = val
    return v


def sources(env=None) -> dict:
    """{place: codes} for each place that names at least one code: `environment`, the host env file's path, the
    checkout's .env path. With `env` given (tests), that mapping alone, as `environment`."""
    if env is not None:
        got = {"environment": _parse(env.get(ENV))}
    else:
        host = Path(os.environ.get("SP_HOST_ENV") or "/etc/sports-predictor/host.env")
        got = {"environment": _parse(os.environ.get(ENV)), str(host): _parse(_env_file(host)),
               str(REPO / ".env"): _parse(_env_file(REPO / ".env"))}
    return {k: v for k, v in got.items() if v}


def held_codes(env=None) -> frozenset:
    """The competition codes SP_SYNC_HOLD names in any place it is read (see the module docstring), upper-cased;
    empty when it is unset or blank everywhere."""
    return frozenset().union(*sources(env).values())


def is_held(code: str | None, env=None) -> bool:
    return bool(code) and code.upper() in held_codes(env)


def held_line(code: str) -> str:
    """The line a held step prints, exactly as addendum 332 item 3 words it."""
    return f"HELD {code.upper()} ({ENV})"
