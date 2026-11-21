"""Background pre-generation pools: keep N ready items per key so requests are served instantly."""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Deque, Dict, Generic, Hashable, Optional, Tuple, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_ENABLED = os.getenv("PREGEN_ENABLED", "1") != "0"
_EXECUTOR = ThreadPoolExecutor(
    max_workers=max(1, int(os.getenv("PREGEN_WORKERS", "3"))),
    thread_name_prefix="pregen",
)


_REGISTRY: "list[PregenPool]" = []


def warm_all() -> None:
    """Start filling every registered pool for its warm keys (called once at app startup)."""
    for pool in _REGISTRY:
        for key in pool.warm_keys:
            pool.fill(key)


def all_stats() -> Dict[str, Dict[str, Dict[str, int]]]:
    return {pool.name: pool.stats() for pool in _REGISTRY}


class PregenPool(Generic[T]):
    """
    Each item is handed out exactly once (popped), so a pooled question is never served twice.
    Producers are responsible for content-level uniqueness (fingerprint history).
    """

    def __init__(
        self,
        name: str,
        producer: Callable[[Hashable], T],
        target: int,
        warm_keys: "tuple[Hashable, ...]" = (),
        max_age_seconds: float = 6 * 3600,
    ) -> None:
        self.warm_keys = warm_keys
        _REGISTRY.append(self)
        self.name = name
        self._producer = producer
        self._target = max(0, target)
        self._max_age = max_age_seconds
        self._lock = threading.Lock()
        self._ready: Dict[Hashable, Deque[Tuple[float, T]]] = {}
        self._in_flight: Dict[Hashable, int] = {}
        self._failures: Dict[Hashable, int] = {}

    def take(self, key: Hashable) -> Optional[T]:
        """Pop a ready item for `key` (or None) and schedule refills either way."""
        item: Optional[T] = None
        now = time.time()
        with self._lock:
            queue = self._ready.get(key)
            while queue:
                created, candidate = queue.popleft()
                if now - created <= self._max_age:
                    item = candidate
                    break
        self.fill(key)
        return item

    def fill(self, key: Hashable) -> None:
        if not _ENABLED or self._target == 0:
            return
        with self._lock:
            ready = len(self._ready.get(key, ()))
            in_flight = self._in_flight.get(key, 0)
            # Back off after repeated failures so a broken provider is not hammered.
            if self._failures.get(key, 0) >= 3:
                return
            missing = self._target - ready - in_flight
            if missing <= 0:
                return
            self._in_flight[key] = in_flight + missing
        for submitted in range(missing):
            try:
                _EXECUTOR.submit(self._produce, key)
            except RuntimeError:  # interpreter shutting down
                with self._lock:
                    self._in_flight[key] = max(0, self._in_flight.get(key, 0) - (missing - submitted))
                return

    def _produce(self, key: Hashable) -> None:
        try:
            item = self._producer(key)
        except Exception as error:
            logger.warning("Pregen %s[%s] failed: %s", self.name, key, error)
            with self._lock:
                self._in_flight[key] = max(0, self._in_flight.get(key, 1) - 1)
                failures = self._failures.get(key, 0) + 1
                self._failures[key] = failures
            if failures == 3:
                timer = threading.Timer(120, self._reset_failures, args=(key,))
                timer.daemon = True
                timer.start()
            return
        with self._lock:
            self._in_flight[key] = max(0, self._in_flight.get(key, 1) - 1)
            self._failures[key] = 0
            self._ready.setdefault(key, deque()).append((time.time(), item))

    def _reset_failures(self, key: Hashable) -> None:
        with self._lock:
            self._failures[key] = 0
        self.fill(key)

    def stats(self) -> Dict[str, Dict[str, int]]:
        with self._lock:
            keys = set(self._ready) | set(self._in_flight)
            return {
                str(k): {"ready": len(self._ready.get(k, ())), "in_flight": self._in_flight.get(k, 0)}
                for k in keys
            }
