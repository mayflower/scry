"""Self-healing patch application (V4).

In this version patches are codegen options; no direct code diffing is needed.
This module exists to keep the API stable when moving to more complex patches.
"""

from __future__ import annotations

from typing import Dict, Any


def merge_codegen_options(
    base: Dict[str, Any], patch: Dict[str, Any]
) -> Dict[str, Any]:
    out = dict(base)
    out.update({k: v for k, v in patch.items() if v is not None})
    return out
