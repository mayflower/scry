#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import json
import requests


BASE = os.getenv("SMARTR_BASE_URL", "http://127.0.0.1:8000")

payload = {
    "nl_request": "Using https://www.parkundride.de/, find the current number of free spaces at Tiefgarage Moosach.",
    "parameters": {"facility": "Tiefgarage Moosach"},
    "schema": {
        "type": "object",
        "properties": {
            "facility": {"type": "string"},
            "free_places": {"type": "integer"}
        }
    },
    "target_urls": ["https://www.parkundride.de/"]
}

try:
    r = requests.post(f"{BASE}/scrape", json=payload, timeout=600)
    r.raise_for_status()
    data = r.json().get("data") or {}
    print(data.get("free_places"))
except Exception as e:
    # Print detail when available to aid debugging
    try:
        body = r.json()
        print(body.get("detail") or str(e))
    except Exception:
        print(str(e))
    sys.exit(1)

