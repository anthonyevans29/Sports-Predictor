"""
Background job runner.

Why threads, not asyncio: our ingestion/training code is all sync (SQLAlchemy
sessions, requests, blocking I/O). Wrapping it in asyncio would require
either rewriting everything as async or marking endpoints as sync and losing
FastAPI's concurrency benefits. A daemon thread per job is simpler.

Why not Celery/RQ: this is a local single-user app. Setting up Redis and a
worker process for what is essentially "run this function in the background"
is overkill. If we ever need durability across restarts, swap to RQ.

Job lifecycle:
    PENDING → RUNNING → SUCCESS | FAILED
                     ↘ CANCELLED (user-requested; jobs only check at safe points)

Status + recent log lines are kept in memory. They survive until the process
restarts. The UI polls /admin/jobs/{job_id} every couple of seconds.
"""
from __future__ import annotations

import logging
import threading
import time
import traceback
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

log = logging.getLogger(__name__)

MAX_LOG_LINES_PER_JOB = 200
MAX_JOBS_RETAINED = 50


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    id: str
    name: str
    description: str
    status: JobStatus = JobStatus.PENDING
    log_lines: deque = field(default_factory=lambda: deque(maxlen=MAX_LOG_LINES_PER_JOB))
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: Any = None
    error: str | None = None

    def append_log(self, msg: str) -> None:
        self.log_lines.append(f"{datetime.utcnow().strftime('%H:%M:%S')} {msg}")

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "log_lines": list(self.log_lines),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "result": str(self.result) if self.result is not None else None,
            "error": self.error,
            "elapsed_seconds": self._elapsed(),
        }

    def _elapsed(self) -> float | None:
        if not self.started_at:
            return None
        end = self.finished_at or datetime.utcnow()
        return (end - self.started_at).total_seconds()


class JobRunner:
    """Singleton-ish job runner. One instance per process."""

    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._order: deque = deque(maxlen=MAX_JOBS_RETAINED)
        self._lock = threading.Lock()

    def submit(self, name: str, description: str, fn: Callable, *args, **kwargs) -> Job:
        job_id = uuid.uuid4().hex[:12]
        job = Job(id=job_id, name=name, description=description)
        with self._lock:
            self._jobs[job_id] = job
            self._order.append(job_id)
            # Trim old jobs that aged out of the deque
            extra = set(self._jobs) - set(self._order)
            for key in extra:
                del self._jobs[key]
        job.append_log(f"queued: {description}")

        thread = threading.Thread(
            target=self._run, args=(job, fn, args, kwargs), daemon=True, name=f"job-{name}"
        )
        thread.start()
        return job

    def _run(self, job: Job, fn: Callable, args: tuple, kwargs: dict) -> None:
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        job.append_log("started")
        try:
            # Pass the job itself as a kwarg so the function can write log lines
            # if it wants. Functions that don't accept `job` ignore it via **kwargs.
            result = fn(*args, job=job, **kwargs)
            job.result = result
            job.status = JobStatus.SUCCESS
            job.append_log(f"completed: {result}" if result is not None else "completed")
        except Exception as e:
            job.status = JobStatus.FAILED
            job.error = str(e)
            job.append_log(f"FAILED: {e}")
            # Capture traceback in the log for debugging
            tb = traceback.format_exc().splitlines()[-5:]
            for line in tb:
                job.append_log(f"  {line}")
            log.exception("Job %s failed", job.name)
        finally:
            job.finished_at = datetime.utcnow()

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list_recent(self, limit: int = 20) -> list[Job]:
        with self._lock:
            ids = list(self._order)
        out: list[Job] = []
        for jid in reversed(ids):
            job = self._jobs.get(jid)
            if job is not None:
                out.append(job)
            if len(out) >= limit:
                break
        return out


# Module-level singleton
runner = JobRunner()
