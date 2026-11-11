"""SP_SYNC_HOLD: a per-competition sync hold the step itself honors (ARCHITECT 2026-11-10 18:55 ET, addendum 332 item
3, verbatim): "THE DURABLE ANSWER is a per-competition sync hold the step itself honors: SP_SYNC_HOLD, a list of
competition codes read by sync-teams and sync-matches, which print "HELD <code> (SP_SYNC_HOLD)" and exit 0 for a listed
code, every chain and timer unchanged, the window and fullseason plans unchanged; a receipt line counts the held
steps." And (addendum 333 item 3(iii), verbatim): "the rule follows the WRITE PATH (_upsert_match), not the step's
name [...] SP_SYNC_HOLD (#921) honors the same path: its design covers intl-sync, or says in its body why not."

The setting is an environment variable: the host's /etc/sports-predictor/host.env (the chain service's
EnvironmentFile, read at each run's start) or the laptop's .env (config.py's load_dotenv). Codes are separated by
commas or blanks and read case-insensitively. Unset or empty holds nothing. Honored by `sync-teams`, `sync-matches`
(every source: the MLB api-sports fallback and the tennis path included, checked before either), `refresh-by-id`
(NCAA, NFL: it writes kickoff, status and scores by id) and `intl-sync` (per code of its plan). A held step writes
nothing for that code and exits 0. sp_run counts the steps that printed the line (sp_run.HELD_LINE).
"""
from __future__ import annotations

import os
import re

ENV = "SP_SYNC_HOLD"
_SPLIT = re.compile(r"[,\s]+")


def held_codes(env=None) -> frozenset:
    """The competition codes SP_SYNC_HOLD names, upper-cased; empty when unset or blank."""
    v = (os.environ if env is None else env).get(ENV) or ""
    return frozenset(x.upper() for x in _SPLIT.split(v.strip()) if x)


def is_held(code: str | None, env=None) -> bool:
    return bool(code) and code.upper() in held_codes(env)


def held_line(code: str) -> str:
    """The line a held step prints, exactly as addendum 332 item 3 words it."""
    return f"HELD {code.upper()} ({ENV})"
