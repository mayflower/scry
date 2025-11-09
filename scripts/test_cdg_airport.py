#!/usr/bin/env python3
"""Charles de Gaulle Airport arrivals test."""

from __future__ import annotations

import json
import os
import sys
from typing import Any


try:
    import requests
except ImportError:
    print("Please install requests: pip install requests", file=sys.stderr)
    sys.exit(1)


BASE_URL = os.getenv("SMARTR_BASE_URL", "http://127.0.0.1:8000")
TIMEOUT = int(os.getenv("SMARTR_TIMEOUT", "300"))


def post_json(path: str, payload: dict[str, Any]) -> requests.Response:
    url = f"{BASE_URL}{path}"
    return requests.post(url, json=payload, timeout=TIMEOUT)


def main() -> None:
    print("\n=== Charles de Gaulle Airport Arrivals Test ===")

    payload = {
        "nl_request": "Go to Paris Aeroport website and find the next arriving flight at Charles de Gaulle. Return flight number, origin city, scheduled arrival time, and current status.",
        "schema": {
            "type": "object",
            "properties": {
                "flight_number": {
                    "type": "string",
                    "description": "Flight number (e.g. AF 123)",
                },
                "origin": {"type": "string", "description": "Origin city/airport"},
                "scheduled_time": {
                    "type": "string",
                    "description": "Scheduled arrival time",
                },
                "status": {"type": "string", "description": "Current flight status"},
            },
        },
        "target_urls": ["https://www.parisaeroport.fr/"],
    }

    print("Request: Find next arriving flight at Charles de Gaulle Airport")
    print(f"Target URL: {payload['target_urls'][0]}")

    r = post_json("/scrape", payload)
    print(f"Status: {r.status_code}")

    try:
        body = r.json()
    except Exception as e:
        print(f"Failed to parse response: {e}")
        print(f"Response: {r.text[:500]}")
        return

    print(f"Job ID: {body.get('job_id')}")
    print(f"Execution log: {body.get('execution_log', [])}")

    data = body.get("data", {})
    if data:
        print("\n=== Flight Information ===")
        print(f"Flight Number: {data.get('flight_number', 'N/A')}")
        print(f"Origin: {data.get('origin', 'N/A')}")
        print(f"Scheduled Time: {data.get('scheduled_time', 'N/A')}")
        print(f"Status: {data.get('status', 'N/A')}")
    else:
        print("No flight data extracted")

    print(f"\nFull data: {json.dumps(data, ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    main()
