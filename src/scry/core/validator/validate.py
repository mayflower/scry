"""JSON Schema validation & normalization (V2+)."""

from __future__ import annotations

from typing import Any, Dict

try:
    import jsonschema
except Exception:  # pragma: no cover
    jsonschema = None  # type: ignore


def _prune_object(schema: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    props = schema.get("properties", {}) or {}
    out: Dict[str, Any] = {}
    for k, v in data.items():
        if k in props:
            out[k] = v
    return out


def normalize_against_schema(
    schema: Dict[str, Any], data: Dict[str, Any]
) -> Dict[str, Any]:
    st = schema.get("type")
    if st == "object" and isinstance(data, dict):
        data = _prune_object(schema, data)
    # Best-effort validation if jsonschema is available
    if jsonschema is not None:
        try:
            jsonschema.validate(instance=data, schema=schema)
        except Exception:
            # Keep best-effort data even if it doesn't fully validate
            pass
    return data
