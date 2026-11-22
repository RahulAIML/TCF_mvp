"""Bounds on the work that can stall the one web worker.

Sync request handlers share Starlette's thread pool. Audio, ffmpeg and provider calls must not
each spawn an unbounded thread, or that pool fills and even /api/version stops answering.
"""
from __future__ import annotations

import os
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor

HEAVY_WORKERS = max(1, int(os.getenv("HEAVY_WORKERS", "1")))
FFMPEG_SLOTS = max(1, int(os.getenv("FFMPEG_CONCURRENCY", "1")))
# How many heavy jobs may be waiting. Past this, a new job fails immediately instead of queueing forever.
MAX_HEAVY_WAITING = max(HEAVY_WORKERS, int(os.getenv("HEAVY_QUEUE", "6")))

HEAVY = ThreadPoolExecutor(max_workers=HEAVY_WORKERS, thread_name_prefix="heavy")
_ffmpeg = threading.BoundedSemaphore(FFMPEG_SLOTS)
_waiting = 0
_waiting_lock = threading.Lock()


class Busy(RuntimeError):
    """The heavy-work queue is full. Callers should answer quickly, not wait."""


def submit(work):
    """Queue work on the heavy pool. Raises Busy when too many jobs are already waiting."""
    global _waiting
    with _waiting_lock:
        if _waiting >= MAX_HEAVY_WAITING:
            raise Busy(f"Heavy work queue is full ({_waiting} waiting).")
        _waiting += 1

    def run():
        global _waiting
        try:
            return work()
        finally:
            with _waiting_lock:
                _waiting -= 1

    try:
        return HEAVY.submit(run)
    except RuntimeError:
        with _waiting_lock:
            _waiting -= 1
        raise


def run_ffmpeg(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    """One ffmpeg at a time (FFMPEG_CONCURRENCY), and it cannot run longer than timeout."""
    timeout = kwargs.pop("timeout", 30)
    with _ffmpeg:
        return subprocess.run(args, timeout=timeout, **kwargs)
