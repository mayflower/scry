#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys

import requests


BASE = os.getenv("SMARTR_BASE_URL", "http://127.0.0.1:8000")
TIMEOUT = int(os.getenv("SMARTR_TIMEOUT", "600"))  # Airport sites can be slow

payload = {
    "nl_request": "Go to the arrivals page and find the next arriving flight with its flight number, origin city, scheduled time, and current status",
    "schema": {
        "type": "object",
        "properties": {
            "flight_number": {"type": "string"},
            "origin": {"type": "string"},
            "scheduled_time": {"type": "string"},
            "status": {"type": "string"},
        },
    },
    "target_urls": ["https://www.munich-airport.de/"],
}

print("Testing Munich Airport arrivals scraping...")
print(f"Target: {payload['target_urls'][0]}")
print(f"Request: {payload['nl_request']}")
print("-" * 60)

try:
    r = requests.post(f"{BASE}/scrape", json=payload, timeout=TIMEOUT)
    r.raise_for_status()

    response = r.json()
    data = response.get("data") or {}

    # Print the execution log for debugging
    if "execution_log" in response:
        print("Execution log (last 5 entries):")
        for log_entry in response["execution_log"][-5:]:
            print(f"  - {log_entry}")
        print()

    # Print the extracted flight data
    print("Next arriving flight:")
    print(f"  Flight Number: {data.get('flight_number', 'N/A')}")
    print(f"  Origin: {data.get('origin', 'N/A')}")
    print(f"  Scheduled Time: {data.get('scheduled_time', 'N/A')}")
    print(f"  Status: {data.get('status', 'N/A')}")

    # Pretty print the full data
    print("\nFull response data:")
    print(json.dumps(data, indent=2, ensure_ascii=False))

except requests.exceptions.Timeout:
    print(f"Error: Request timed out after {TIMEOUT} seconds")
    sys.exit(1)
except requests.exceptions.RequestException as e:
    print(f"Error: Request failed - {e}")
    # Try to extract error details from response
    try:
        if hasattr(e, "response") and e.response is not None:
            body = e.response.json()
            if "detail" in body:
                print(f"Detail: {body['detail']}")
            if "error" in body:
                print(f"Error: {body['error']}")
    except Exception:
        pass
    sys.exit(1)
except Exception as e:
    print(f"Unexpected error: {e}")
    sys.exit(1)
