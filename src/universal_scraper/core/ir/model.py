"""ScrapePlan IR definitions (introduced in V2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Union


@dataclass
class Navigate:
    url: str


@dataclass
class Click:
    selector: str


@dataclass
class Fill:
    selector: str
    text: str


@dataclass
class WaitFor:
    selector: str
    state: str = "visible"  # visible|hidden|attached|detached


PlanStep = Union[Navigate, Click, Fill, WaitFor]


@dataclass
class ScrapePlan:
    steps: List[PlanStep]
    notes: Optional[str] = None
