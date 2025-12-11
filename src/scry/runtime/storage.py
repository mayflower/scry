from __future__ import annotations

from pathlib import Path


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def job_artifact_paths(base_dir: Path, job_id: str) -> tuple[Path, Path, Path]:
    screenshots = base_dir / "screenshots" / job_id
    generated = base_dir / "generated_code"
    html = base_dir / "html"
    ensure_dir(screenshots)
    ensure_dir(generated)
    ensure_dir(html)
    return screenshots, generated, html


def data_artifact_path(base_dir: Path, job_id: str) -> Path:
    p = base_dir / "data"
    ensure_dir(p)
    return p / f"{job_id}.json"
