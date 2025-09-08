from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    artifacts_root: str = os.getenv("ARTIFACTS_ROOT", "artifacts")
    headless: bool = _env_bool("HEADLESS", True)
    nav_backend: str = os.getenv("NAV_BACKEND", "browser_use")  # browser_use|playwright
    screenshot_dir: str = os.getenv("SCREENSHOT_DIR", "artifacts/screenshots")
    generated_code_dir: str = os.getenv(
        "GENERATED_CODE_DIR", "artifacts/generated_code"
    )
    html_snapshots_dir: str = os.getenv("HTML_SNAPSHOTS_DIR", "artifacts/html")
    event_backend: str = os.getenv("EVENT_BACKEND", "inmemory")
    redis_url: str | None = os.getenv("REDIS_URL")
    worker_concurrency: int = int(os.getenv("WORKER_CONCURRENCY", "1"))
    max_repair_attempts: int = int(os.getenv("MAX_REPAIR_ATTEMPTS", "20"))


settings = Settings()
