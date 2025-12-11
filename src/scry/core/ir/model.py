"""ScrapePlan IR definitions (introduced in V2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union


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


@dataclass
class Validate:
    """Validation checkpoint to detect if page state is as expected."""

    selector: str
    expected_text: str | None = None
    expected_count: int | None = None
    is_critical: bool = False  # If true, failure triggers self-healing
    description: str = ""  # What this validation checks
    validation_type: str = "presence"  # presence|text|count|absence


@dataclass
class Select:
    """Select option from dropdown menu."""

    selector: str
    value: str  # Option value or visible text to select


@dataclass
class Hover:
    """Hover over element to trigger hover effects."""

    selector: str


@dataclass
class KeyPress:
    """Press keyboard key, optionally on specific element."""

    key: str  # e.g., "Enter", "Escape", "Tab", "ArrowDown"
    selector: str | None = None  # If targeting specific element


@dataclass
class Upload:
    """Upload file to file input."""

    selector: str
    file_path: str  # Path to file to upload


PlanStep = Union[
    Navigate, Click, Fill, WaitFor, Validate, Select, Hover, KeyPress, Upload
]


@dataclass
class ScrapePlan:
    steps: list[PlanStep]
    notes: str | None = None
