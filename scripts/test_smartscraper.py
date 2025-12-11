#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

try:
    import requests
except ImportError:
    print("Please install requests: pip install requests", file=sys.stderr)
    sys.exit(1)


BASE_URL = os.getenv("SMARTR_BASE_URL", "http://127.0.0.1:8000")
TIMEOUT = int(os.getenv("SMARTR_TIMEOUT", "180"))


def post_json(path: str, payload: dict[str, Any]) -> requests.Response:
    url = f"{BASE_URL}{path}"
    return requests.post(url, json=payload, timeout=TIMEOUT)


def get_json(path: str) -> dict[str, Any]:
    url = f"{BASE_URL}{path}"
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def run_sync_case(name: str, payload: dict[str, Any]) -> None:
    print(f"\n=== SYNC: {name} ===")
    r = post_json("/scrape", payload)
    print("status", r.status_code)
    try:
        body = r.json()
    except Exception:
        print(r.text[:500])
        return
    print("keys", list(body.keys()))
    print("log_tail", body.get("execution_log", [])[-8:])
    print("data", json.dumps(body.get("data"), ensure_ascii=False)[:300])


def run_async_case(name: str, payload: dict[str, Any]) -> None:
    print(f"\n=== ASYNC: {name} ===")
    r = post_json("/scrape/async", payload)
    print("enqueue status", r.status_code)
    jid = r.json().get("job_id")
    if not jid:
        print("enqueue failed", r.text)
        return
    print("job_id", jid)
    # Poll
    t0 = time.time()
    while time.time() - t0 < TIMEOUT:
        body = get_json(f"/jobs/{jid}")
        if "execution_log" in body:
            print("keys", list(body.keys()))
            print("log_tail", body.get("execution_log", [])[-8:])
            print("data", json.dumps(body.get("data"), ensure_ascii=False)[:300])
            return
        time.sleep(1.0)
    print("timeout waiting for job")


def main() -> None:
    cases: list[dict[str, Any]] = []

    # Baseline example.com
    cases.append(
        {
            "name": "example.com baseline",
            "mode": "sync",
            "payload": {
                "nl_request": "Open and extract basic info",
                "schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "links": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "target_urls": ["https://example.com"],
            },
        }
    )

    # Park+Ride: free places at Tiefgarage Moosach
    cases.append(
        {
            "name": "parkundride Tiefgarage Moosach free places (sync)",
            "mode": "sync",
            "payload": {
                "nl_request": "Using https://www.parkundride.de/, find the current number of free spaces at Tiefgarage Moosach.",
                "parameters": {"facility": "Tiefgarage Moosach"},
                "schema": {
                    "type": "object",
                    "properties": {
                        "facility": {"type": "string"},
                        "free_places": {"type": "integer"},
                    },
                },
                "target_urls": ["https://www.parkundride.de/"],
            },
        }
    )

    # Mayflower: employees
    cases.append(
        {
            "name": "mayflower employees (async)",
            "mode": "async",
            "payload": {
                "nl_request": "From https://mayflower.de/ find the number of employees (current).",
                "schema": {
                    "type": "object",
                    "properties": {"employees": {"type": "integer"}},
                },
                "target_urls": ["https://mayflower.de/"],
            },
        }
    )

    for c in cases:
        if c["mode"] == "async":
            run_async_case(c["name"], c["payload"])  # type: ignore[arg-type]
        else:
            run_sync_case(c["name"], c["payload"])  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
