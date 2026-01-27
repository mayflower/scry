from __future__ import annotations

import asyncio
import json
import logging
import os

from .api.dto import ScrapeRequest
from .core.executor.runner import run_job, run_job_with_id
from .runtime.events import get_bus

logger = logging.getLogger(__name__)


def _worker_loop() -> None:
    bus = get_bus()
    while True:
        msg = bus.dequeue(timeout=5)
        if not msg:
            continue
        try:
            job_id = msg.get("job_id")
            req = ScrapeRequest(**msg["request"])  # type: ignore[index]
            # Run async functions from sync worker thread
            if job_id:
                result = asyncio.run(run_job_with_id(job_id, req))
            else:
                result = asyncio.run(run_job(req))
            bus.set_result(result.job_id, json.loads(result.model_dump_json()))
        except Exception:
            logger.exception("Worker job failed for message: %s", msg.get("job_id", "unknown"))


def main() -> None:
    import threading

    concurrency = int(os.getenv("WORKER_CONCURRENCY", "1"))
    threads = []
    for _ in range(max(1, concurrency)):
        t = threading.Thread(target=_worker_loop, daemon=True)
        t.start()
        threads.append(t)
    # Keep the main thread alive
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
