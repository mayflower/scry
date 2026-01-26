"""JSON Schema validation & normalization (V2+)."""

from __future__ import annotations

from typing import Any

try:
    import jsonschema  # type: ignore[import-untyped]
except Exception:  # pragma: no cover
    jsonschema = None  # type: ignore[assignment]


def _prune_object(schema: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    props = schema.get("properties", {}) or {}
    out: dict[str, Any] = {}
    for k, v in data.items():
        if k in props:
            out[k] = v
    return out


def normalize_against_schema(schema: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    st = schema.get("type")
    if st == "object" and isinstance(data, dict):
        data = _prune_object(schema, data)
    # Best-effort validation if jsonschema is available
    if jsonschema is not None:
        try:
            jsonschema.validate(instance=data, schema=schema)
        except Exception:  # noqa: S110 - keep best-effort data even if it doesn't validate
            pass
    return data
