"""Retry transient provider and network failures. Validation errors are not retried.

A 429, 5xx, or timeout from Gemini or ElevenLabs is treated as a blip: the same call is
repeated with exponential backoff and jitter. A bad request or a failed content check is raised
immediately so a caller does not wait on something that cannot succeed.
"""
from __future__ import annotations

import logging
import os
import random
import time
from typing import Callable, TypeVar

logger = logging.getLogger("tcf.resilience")

T = TypeVar("T")

_TRANSIENT = (
    "429",
    "500",
    "502",
    "503",
    "504",
    "timeout",
    "timed out",
    "deadline",
    "unavailable",
    "resource_exhausted",
    "resource exhausted",
    "connection",
    "reset by peer",
    "temporarily",
    "quota",
    "rate limit",
    "overloaded",
)


def is_transient(error: BaseException) -> bool:
    text = f"{type(error).__name__} {error}".lower()
    # A 400/401/403/404 is the request, not a blip, even if the body mentions "500 characters" or "quota".
    if any(code in text for code in ("http 400", "http 401", "http 403", "http 404", "http 422")):
        return False
    return any(marker in text for marker in _TRANSIENT)


def sleep_backoff(attempt: int, base: float = 0.35, cap: float = 8.0) -> None:
    """Sleep for attempt 0, 1, 2… with jitter. RESILIENCE_DELAY_SCALE=0 skips the wait in tests."""
    scale = float(os.getenv("RESILIENCE_DELAY_SCALE", "1"))
    if scale <= 0:
        return
    delay = min(cap, base * (2 ** attempt))
    delay *= 0.5 + random.random()
    time.sleep(delay * scale)


def retry(func: Callable[[], T], *, attempts: int = 4, base: float = 0.35, cap: float = 8.0) -> T:
    """Call func until it returns or the error is not transient."""
    last: BaseException | None = None
    for attempt in range(max(1, attempts)):
        try:
            return func()
        except Exception as error:
            last = error
            if attempt == attempts - 1 or not is_transient(error):
                raise
            logger.warning("Transient failure (attempt %s/%s): %s", attempt + 1, attempts, error)
            sleep_backoff(attempt, base, cap)
    assert last is not None
    raise last
