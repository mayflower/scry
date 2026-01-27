from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from ..ir.model import PlanStep


@dataclass
class ExplorationResult:
    steps: list[PlanStep]
    html_pages: list[str]
    screenshots: list[Path]
    urls: list[str]
    data: dict[str, Any] | None = None
