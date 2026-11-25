#!/usr/bin/env python3
"""LAPTOP side, nightly (H0-14 second layer, ruled 2026-09-27): pull the host's
newest daily .backup over the tailnet into the laptop's own backed-up disk.
$0 and off-provider.

    python deploy/hosting/pull_backup.py [--host sp-vps-1] [--dest ~/sp-backups]

- Lists the host's backup dir over ssh and takes the newest DAILY
  (prerefresh copies are not pulled).
- scp's the file and its .sha256 sidecar to <dest>/<name>.partial.
- Verifies the sha256 against the sidecar, and runs a read-only
  integrity_check on the copy, opened ?mode=ro&immutable=1 (a WAL copy with
  no -shm beside it; addendum 68 item 2, #517).
- Only then renames it into place (mode 0600) and appends a receipt
  (kind "pull") to this machine's receipts log.
- Already pulled with the same sha = a receipted no-op.
- Refuses a --dest under the checkout's data/ (law 5).
- The laptop copy is never pruned automatically.
Installed as a launchd job by scripts/setup_backup_pull.sh.

THE JOB TELLS (ARCHITECT 2026-11-25, addendum 552 item 3, DEV 3's plan as ruled; the
nine points on #1053 read by addendum 554 item 2):
- ssh and scp carry ConnectTimeout=15, below the 60-second kill, so a night the host
  does not answer ends with ssh's own message, not a silent timeout (3(f)).
- Every receipt names its STAGE (list, sidecar, copy, verify, place, done), the
  redacted last lines of ssh's or scp's message (the host and user replaced), and
  the error as its class, exit code and stage; the exception's text, which carries
  the command with the user and host, is not stored (3(f); 554 item 2(c)).
- Every receipt names the NEWEST VERIFIED COPY in --dest and its age: a daily name
  with its .sha256 beside it, never a partial, found by the names alone (no
  database opened, never re-hashed); the age from the name's own date (00:00Z of
  it, or its _HHMMSS), never from the file's time (3(c); 554 item 2(d)).
- ONE NOTICE when that copy is older than 3 days, one more for each further 3 days
  it stays so; no verified copy at all is a step of its own. Told only when the
  card (NTFY_CARD_TOPIC) or, failing it, the operator's topic (NTFY_TOPIC) took
  it; never the screen alone (3(d)). A step no channel took is sent again on the
  next run. Its text names no host (3(f)). Every run tells by age, a good pull of
  an old copy included.
- The exit stays 1 on a failed night; a notice never changes it (3(f)).
- The receipt's "from" and the printed line keep the host name: they are the
  laptop's own record of its own run, not a notice (554 item 2(c)).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sp_common as c  # noqa: E402

REMOTE_DIR = "/var/backups/sports-predictor"
DAILY = re.compile(r"^sports_\d{4}-\d{2}-\d{2}(_\d{6})?\.db$")
# 552 item 3(f): ssh's connect timeout below the 60-second kill (pull_exports.py's precedent)
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=15"]
SSH_KILL_S, SCP_KILL_S = 60, 1800
TAIL_LINES, TAIL_CHARS = 2, 300
STEP_DAYS = 3                          # 552 item 3(c): one notice past 3 days, one more each further 3 days
NO_COPY = "none"                       # the step of a folder holding no verified copy at all
NOTICE_TITLE = "Backup pull"
_NAME_TIME = re.compile(r"^sports_(\d{4})-(\d{2})-(\d{2})(?:_(\d{2})(\d{2})(\d{2}))?\.db$")


class PullError(RuntimeError):
    """A failure this script names itself: its text is its own and carries no host, user or command."""


class StepFailed(Exception):
    """ssh or scp answered with a non-zero exit: the code and ssh's own message (stderr) are kept."""

    def __init__(self, returncode: int, stderr):
        super().__init__(f"exit {returncode}")
        self.returncode, self.stderr = returncode, stderr


def newest_daily(names: list[str]) -> str | None:
    """Lexical max over daily names: a same-day re-run's _HHMMSS suffix sorts
    after the plain name ('_' > '.'), so it is correctly the newer one."""
    daily = sorted(n.strip() for n in names if DAILY.match(n.strip()))
    return daily[-1] if daily else None


def verify_and_place(partial: Path, sidecar: Path, final: Path, rec: dict | None = None) -> dict:
    """`rec`, when given, has its stage moved to "place" once the copy is verified (552 item 3(f))."""
    want = sidecar.read_text().split()[0]
    got = c.sha256_file(partial)
    if got != want:
        raise PullError(f"sha256 mismatch: sidecar {want[:12]} vs pulled {got[:12]}")
    integ = c.copy_integrity(partial)     # the pulled COPY, immutable (addendum 68 item 2, #517); never the live DB
    if integ != "ok":
        raise PullError(f"integrity_check: {integ}")
    if rec is not None:
        rec["stage"] = "place"
    os.chmod(partial, 0o600)
    partial.rename(final)
    sidecar.rename(final.with_name(final.name + ".sha256"))
    return {"sha256": got, "integrity": integ, "bytes": final.stat().st_size}


def copy_time(name: str) -> datetime | None:
    """The time a daily name stands for, UTC (the host names its dailies by the UTC date, sp_backup.py): 00:00Z of its
    date, or its _HHMMSS. None for a name that is not a daily or not a real date. 00:00Z makes a plain name's age the
    larger reading, so a notice comes sooner, never later (#1053 P6)."""
    m = _NAME_TIME.match(name)
    if not m:
        return None
    try:
        return datetime(*(int(g) for g in m.groups() if g is not None), tzinfo=timezone.utc)
    except ValueError:
        return None


def newest_verified(dest: Path) -> str | None:
    """552 item 3(c): "a daily name with its sha256 beside it, never a partial". By the names alone: no database is
    opened and nothing is hashed again (the sidecar is put in place only after the copy's sha256 and integrity check
    passed, verify_and_place; #1053 P5). A name whose date does not read is passed over."""
    try:
        names = [p.name for p in dest.iterdir()]
    except OSError:
        return None
    have = set(names)
    ok = [n for n in names if DAILY.match(n) and f"{n}.sha256" in have and copy_time(n) is not None
          and (dest / n).is_file() and (dest / f"{n}.sha256").is_file()]
    return max(ok) if ok else None


def copy_age(dest: Path, now: datetime) -> dict | None:
    """The newest verified copy's name and age (#1053 P5-P6), or None when the folder holds none."""
    name = newest_verified(dest)
    if name is None:
        return None
    hours = (now - copy_time(name)).total_seconds() / 3600
    return {"name": name, "age_hours": round(hours, 1), "age_days": round(hours / 24, 2)}


def notice_step(newest: dict | None) -> int | str | None:
    """The notice step (#1053 P7): None while the newest verified copy is 3 days old or less; else floor(age / 3
    days), 1 from past 3 days; NO_COPY when there is no verified copy at all."""
    if newest is None:
        return NO_COPY
    days = newest["age_hours"] / 24
    return int(days // STEP_DAYS) if days > STEP_DAYS else None


def _scrub(text: str, host: str, user: str) -> str:
    """A message for the receipt: redacted (c.redact: the secrets), then the host and the user replaced (552 item
    3(f); #1053 P4), any IP address with them; the class name only if redact itself cannot run."""
    try:
        text = c.redact(text)
    except Exception as e:  # noqa: BLE001 - a .env that does not decode (laptop_routine._redacted's rule)
        return f"(the message could not be redacted: {type(e).__name__})"
    if host:
        if user:
            text = text.replace(f"{user}@{host}", "<user>@<host>")
        text = text.replace(host, "<host>")
    if user:
        text = re.sub(rf"(?<![\w.-]){re.escape(user)}(?=@)", "<user>", text)
    text = re.sub(r"(?<![\w.:])\d{1,3}(?:\.\d{1,3}){3}(?![\w.])", "<addr>", text)
    # an IPv6 address: hex groups and colons holding "::" or at least five colons (a clock's "12:34:56" is not one)
    return re.sub(r"(?<![\w:])[0-9A-Fa-f:]*:[0-9A-Fa-f:]*:[0-9A-Fa-f:]*(?![\w:])",
                  lambda m: "<addr>" if "::" in m.group(0) or m.group(0).count(":") >= 5 else m.group(0), text)


def _tail(stderr, host: str, user: str) -> str | None:
    """The last TAIL_LINES lines of ssh's or scp's message, scrubbed, at most TAIL_CHARS."""
    if stderr is None:
        return None
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", "replace")
    lines = [ln.rstrip() for ln in str(stderr).splitlines() if ln.strip()]
    return _scrub("\n".join(lines[-TAIL_LINES:]), host, user)[:TAIL_CHARS] if lines else None


def _run(cmd: list[str], kill_s: int):
    """One ssh or scp: its return code read here (no check=True), its message kept for the receipt."""
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=kill_s)
    if r.returncode != 0:
        raise StepFailed(r.returncode, r.stderr)
    return r


def _ssh(remote: str, command: str):
    return _run(["ssh", *SSH_OPTS, remote, command], SSH_KILL_S)


def _past_notices(copy: str | None, step) -> list[dict]:
    """The notices earlier pull receipts in this machine's receipts log record for this copy and step."""
    p = c.receipts_path()
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        n = r.get("notice") if isinstance(r, dict) and r.get("kind") == "pull" else None
        if isinstance(n, dict) and n.get("copy") == copy and n.get("step") == step:
            out.append(n)
    return out


def notice_text(newest: dict | None, rec: dict, machine: str) -> str:
    """The notice's words: the copy's name and age, the run's stage and its error's class, the machine by its role.
    No host name (552 item 3(f))."""
    head = (f"The newest verified copy of the host's backup on this machine is {newest['age_days']:.1f} days old "
            f"({newest['name']}).") if newest else "This machine holds no verified copy of the host's backup."
    last = "pulled" if rec.get("exit") == 0 else f"failed at {rec.get('stage')} ({rec.get('error_class')})"
    return f"{head}\nTonight's pull: {last}.\n{machine}"


def tell(newest: dict | None, rec: dict) -> dict | None:
    """552 item 3(c)-(d): the notice for this run, or None when none is due (the copy is fresh, or this step was
    already taken). The card first; the operator's topic when the card did not take it; never the screen. The
    senders are closing's own (they never record the URL or the message)."""
    step = notice_step(newest)
    if step is None:
        return None
    copy = newest["name"] if newest else None
    if any(n.get("channel") for n in _past_notices(copy, step)):
        return None
    import closing
    text = notice_text(newest, rec, closing.machine_line())
    n = {"copy": copy, "step": step, "text": text}
    try:
        n["card"] = closing.page_phone(NOTICE_TITLE, text, "high")
    except Exception as e:  # noqa: BLE001
        n["card"] = {"accepted": False, "error": type(e).__name__}
    took = "card" if n["card"].get("accepted") is True else None
    if took is None:
        try:
            n["operator"] = closing.page_operator(NOTICE_TITLE, text)
        except Exception as e:  # noqa: BLE001
            n["operator"] = {"accepted": False, "error": type(e).__name__}
        took = "operator" if n["operator"].get("accepted") is True else None
    n["channel"] = took
    return n


def main(argv=None, now: datetime | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pull the host's newest daily .backup.")
    ap.add_argument("--host", default="sp-vps-1")
    ap.add_argument("--user", default="sp")
    ap.add_argument("--dest", type=Path, default=Path.home() / "sp-backups")
    a = ap.parse_args(argv)
    dest = a.dest.expanduser()
    c.refuse_under_data(dest)
    dest.mkdir(parents=True, exist_ok=True)
    remote = f"{a.user}@{a.host}"
    rec = {"kind": "pull", "exit": 1, "from": a.host, "file": None, "stage": "list"}
    try:
        name = newest_daily(_ssh(remote, f"ls -1 {REMOTE_DIR}").stdout.splitlines())
        if name is None:
            raise PullError("no daily backup on the host")
        rec.update(file=name, stage="sidecar")
        final = dest / name
        side = _ssh(remote, f"cat {REMOTE_DIR}/{name}.sha256").stdout.split()
        if not side:
            raise PullError("the host's sidecar is empty")
        side_remote = side[0]
        if final.exists() and c.sha256_file(final) == side_remote:
            rec.update(exit=0, sha256=side_remote, note="already present", stage="done")
        else:
            rec["stage"] = "copy"
            partial, sidecar = dest / (name + ".partial"), dest / (name + ".sha256.partial")
            for src, dst in ((name, partial), (name + ".sha256", sidecar)):
                _run(["scp", "-q", *SSH_OPTS, f"{remote}:{REMOTE_DIR}/{src}", str(dst)], SCP_KILL_S)
            rec["stage"] = "verify"
            rec.update(verify_and_place(partial, sidecar, final, rec), exit=0)
            rec["stage"] = "done"
    except Exception as e:  # receipt first, then fail loudly
        # 552 item 3(f): the class, the exit code and the stage; the exception's own text carries the command with
        # the user and the host, so it is not stored; ssh's message, scrubbed, is
        rec["error_class"] = type(e).__name__
        code = getattr(e, "returncode", None)
        own = _scrub(str(e), a.host, a.user) if isinstance(e, PullError) else None
        rec["error"] = (f"{type(e).__name__} at {rec['stage']}" + (f", exit {code}" if code is not None else "")
                        + (f": {own}" if own else ""))[:TAIL_CHARS]
        tail = _tail(getattr(e, "stderr", None), a.host, a.user)
        if tail:
            rec["ssh_tail"] = tail
        for p in dest.glob("*.partial*"):            # the .partial and anything beside it (addendum 72 item 4)
            p.unlink(missing_ok=True)
    now = now or c.utc_now()
    newest = None
    try:
        newest = copy_age(dest, now)
    except Exception as e:  # noqa: BLE001 - the age is read best effort; the receipt is still written
        rec["newest_copy_error"] = type(e).__name__
    rec["newest_copy"] = newest
    try:                                             # in its own try: a notice never changes the pull's exit
        n = tell(newest, rec)
        if n is not None:
            rec["notice"] = n
    except Exception as e:  # noqa: BLE001
        rec["notice"] = {"copy": newest["name"] if newest else None, "step": notice_step(newest), "channel": None,
                         "error": type(e).__name__}
    c.append_receipt(rec)
    age = f" · newest verified copy {newest['name']} {newest['age_days']:.1f}d" if newest else \
        " · no verified copy held"
    told = f" · notice {rec['notice']['channel'] or 'NOT TAKEN'}" if rec.get("notice") else ""
    print(f"{'✓' if rec['exit'] == 0 else '✗'} pull {rec['file']} from {a.host}: "
          f"sha256={(rec.get('sha256') or '-')[:16]} {rec.get('note') or rec.get('error') or ''}{age}{told}")
    return rec["exit"]


if __name__ == "__main__":
    sys.exit(main())
