"""Event bus (in-memory V1; Redis V3).

Expose a minimal queue interface used by the worker in V3.
"""

from __future__ import annotations

import json
import os
import queue
import threading
from typing import Any


JOB_QUEUE = "scrape_jobs"


class InMemoryBus:
    def __init__(self) -> None:
        self._q: queue.Queue[str] = queue.Queue()
        self._results: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def enqueue(self, payload: dict[str, Any]) -> None:
        self._q.put(json.dumps(payload))

    def dequeue(self, timeout: float | None = None) -> dict[str, Any] | None:
        try:
            msg = self._q.get(timeout=timeout)
        except queue.Empty:
            return None
        return json.loads(msg)

    def set_result(self, job_id: str, result: dict[str, Any]) -> None:
        with self._lock:
            self._results[job_id] = result

    def get_result(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._results.get(job_id)


class RedisBus:
    def __init__(self, url: str) -> None:
        import redis  # lazy import

        self._r = redis.Redis.from_url(url, decode_responses=True)

    def enqueue(self, payload: dict[str, Any]) -> None:
        self._r.rpush(JOB_QUEUE, json.dumps(payload))

    def dequeue(self, timeout: float | None = None) -> dict[str, Any] | None:
        to = int(timeout) if timeout else 0
        item = self._r.blpop([JOB_QUEUE], timeout=to)
        if not item:
            return None
        _, msg = item  # type: ignore[misc]
        if isinstance(msg, bytes):
            msg = msg.decode("utf-8")
        return json.loads(msg)

    def set_result(self, job_id: str, result: dict[str, Any]) -> None:
        key = f"job:{job_id}:result"
        self._r.set(key, json.dumps(result), ex=3600)

    def get_result(self, job_id: str) -> dict[str, Any] | None:
        key = f"job:{job_id}:result"
        val = self._r.get(key)
        return json.loads(val) if val else None  # type: ignore[arg-type]


def get_bus():
    backend = os.getenv("EVENT_BACKEND", "inmemory")
    if backend == "redis":
        url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        return RedisBus(url)
    # Singleton per-process for in-memory backend so API and worker threads share state
    global _INMEMORY_SINGLETON
    try:
        _INMEMORY_SINGLETON
    except NameError:
        _INMEMORY_SINGLETON = InMemoryBus()  # type: ignore[var-annotated]
    return _INMEMORY_SINGLETON
