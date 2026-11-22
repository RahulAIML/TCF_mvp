"""Listening audio jobs.

A long interview can take longer than the host's request limit (~100 s). The HTTP call returns
immediately with a job id; synthesis continues in this process and the client polls. A finished
file is returned on the first response when it is already cached or finishes within a few seconds.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from typing import Any, Callable

import limits

logger = logging.getLogger("tcf.audio_jobs")

# Short on purpose: the request thread is one of the few that can answer /api/version.
# The file keeps generating in the heavy pool and the client polls.
INLINE_WAIT_SECONDS = float(os.getenv("AUDIO_INLINE_WAIT_SECONDS", "2"))
_KEEP_SECONDS = 15 * 60

_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}


def _sweep(now: float) -> None:
    stale = [key for key, job in _jobs.items() if now - job["created"] > _KEEP_SECONDS]
    for key in stale:
        _jobs.pop(key, None)


def submit(work: Callable[[], dict[str, Any]]) -> str:
    """Start work() on a daemon thread. work() returns {"audio_url", "voices"}."""
    job_id = uuid.uuid4().hex
    job: dict[str, Any] = {
        "id": job_id,
        "status": "pending",
        "audio_url": None,
        "voices": [],
        "error": None,
        "created": time.time(),
        "event": threading.Event(),
    }
    with _lock:
        _sweep(job["created"])
        _jobs[job_id] = job

    def run() -> None:
        try:
            result = work()
            job["audio_url"] = result.get("audio_url")
            job["voices"] = result.get("voices") or []
            job["status"] = "ready" if job["audio_url"] else "failed"
            if not job["audio_url"]:
                job["error"] = "empty audio"
        except Exception as error:
            logger.exception("Listening audio job %s failed: %s", job_id, error)
            job["status"] = "failed"
            job["error"] = f"{type(error).__name__}: {error}"
        finally:
            job["event"].set()

    try:
        limits.submit(run)
    except limits.Busy as error:
        job["status"] = "failed"
        job["error"] = str(error)
        job["event"].set()
    return job_id


def snapshot(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        return {
            "job_id": job_id,
            "status": job["status"],
            "audio_url": job["audio_url"],
            "voices": list(job["voices"]),
            "error": job.get("error"),
        }


def wait(job_id: str, timeout: float) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
    if job is None:
        return None
    job["event"].wait(timeout)
    return snapshot(job_id)
