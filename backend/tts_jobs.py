"""Text-to-speech jobs that survive a server restart.

A job is written to the database and also kept in memory while this process runs it. A row that says "pending"
but is not in this process's memory belongs to a process that has since died, so it is reported as interrupted at
once, and the page can start it again instead of waiting for something that will never finish.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable, Optional

from database import SessionLocal
from models import TtsJob

logger = logging.getLogger("tts_jobs")

INTERRUPTED = "interrupted"
_lock = threading.Lock()
_live: dict[str, dict[str, Any]] = {}
_MAX_LIVE = 200


def _fields(job: dict[str, Any]) -> dict[str, Any]:
    return {k: job.get(k) for k in ("status", "audio_url", "error", "total_parts", "done_parts")}


def _write(job_id: str, job: dict[str, Any], create: bool = False) -> None:
    """Best effort: a database hiccup must never fail the generation itself."""
    db = SessionLocal()
    try:
        row = None if create else db.get(TtsJob, job_id)
        if row is None:
            row = TtsJob(id=job_id, chars=int(job.get("chars") or 0), created_at=datetime.utcnow())
            db.add(row)
        row.status = job["status"]
        row.audio_url = job.get("audio_url")
        row.error = (job.get("error") or None) and str(job["error"])[:300]
        row.total_parts = int(job.get("total_parts") or 1)
        row.done_parts = int(job.get("done_parts") or 0)
        row.updated_at = datetime.utcnow()
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("Could not save TTS job %s", job_id)
    finally:
        db.close()


def create(job_id: str, total_parts: int, chars: int) -> None:
    job = {"status": "pending", "audio_url": None, "error": None, "total_parts": total_parts, "done_parts": 0, "chars": chars}
    with _lock:
        if len(_live) >= _MAX_LIVE:
            for key in [k for k, v in _live.items() if v["status"] != "pending"][: _MAX_LIVE // 2]:
                _live.pop(key, None)
        _live[job_id] = job
    _write(job_id, job, create=True)


def update(job_id: str, **changes: Any) -> None:
    with _lock:
        job = _live.get(job_id)
        if job is None:
            return
        job.update(changes)
        snapshot = dict(job)
    _write(job_id, snapshot)


def get(job_id: str) -> Optional[dict[str, Any]]:
    with _lock:
        job = _live.get(job_id)
        if job is not None:
            return _fields(job)
    db = SessionLocal()
    try:
        row = db.get(TtsJob, job_id)
        if row is None:
            return None
        if row.status == "pending":
            # Not running in this process any more: the server restarted while it was being made.
            row.status, row.error, row.updated_at = "error", INTERRUPTED, datetime.utcnow()
            db.commit()
        return {
            "status": row.status,
            "audio_url": row.audio_url,
            "error": row.error,
            "total_parts": row.total_parts,
            "done_parts": row.done_parts,
        }
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("Could not read TTS job %s", job_id)
        return None
    finally:
        db.close()


# A long recording gets its own single lane, so it never holds the one slot short audio (listening) needs.
_LONG = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tts-long")
_MAX_LONG_WAITING = 2
_long_waiting = 0
_long_lock = threading.Lock()


class LongBusy(RuntimeError):
    """Another long recording is already being made and the line is full."""


def submit_long(work: Callable[[], None]) -> None:
    global _long_waiting
    with _long_lock:
        if _long_waiting >= _MAX_LONG_WAITING:
            raise LongBusy("Long audio queue is full.")
        _long_waiting += 1

    def run() -> None:
        global _long_waiting
        try:
            work()
        finally:
            with _long_lock:
                _long_waiting -= 1

    try:
        _LONG.submit(run)
    except RuntimeError:
        with _long_lock:
            _long_waiting -= 1
        raise
