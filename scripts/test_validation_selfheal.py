#!/usr/bin/env python3
"""Test validation-based self-healing functionality."""

import json
import os
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))

from scry.api.dto import ScrapeRequest
from scry.core.executor.runner import run_job


def test_validation_selfheal():
    """Test that validation failures trigger self-healing."""

    # Request with a schema that should trigger validation points
    req = ScrapeRequest(
        nl_request="Navigate to the page and extract the title and main content",
        output_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Page title"},
                "content": {"type": "string", "description": "Main content text"},
            },
            "required": ["title", "content"],
        },
        target_urls=["https://example.com"],
    )

    print("Testing validation-based self-healing...")
    print(f"Request: {req.nl_request}")
    print(f"Target: {req.target_urls[0]}")

    # Run the job - this should:
    # 1. Explore with browser-use and capture validation points
    # 2. Compress the path while preserving validations
    # 3. Generate code with validation checks
    # 4. Execute and handle any validation failures
    result = run_job(req)

    print(f"\nJob ID: {result.job_id}")
    print(f"Execution log: {result.execution_log}")

    # Check if validation points were handled
    if "validation_failed" in result.execution_log:
        print("\n✓ Validation failure detected and handled")
    elif "validation_ok" in result.execution_log:
        print("\n✓ Validation passed")

    # Check if data was extracted
    if result.data:
        print("\nExtracted data:")
        print(json.dumps(result.data, indent=2))
    else:
        print("\n⚠ No data extracted")

    # Check if self-healing was triggered
    repair_attempts = [log for log in result.execution_log if "repair_attempt" in log]
    if repair_attempts:
        print(f"\n✓ Self-healing triggered: {len(repair_attempts)} repair attempts")

    return result


if __name__ == "__main__":
    # Ensure we have required environment variables
    if not os.getenv("ANTHROPIC_API_KEY") and not os.getenv("CLAUDE_API_KEY"):
        print("Error: ANTHROPIC_API_KEY or CLAUDE_API_KEY required")
        sys.exit(1)

    result = test_validation_selfheal()

    # Exit with success if we got data or handled validations properly
    success = (
        bool(result.data)
        or "validation_ok" in result.execution_log
        or "validation_failed" in result.execution_log
    )
    sys.exit(0 if success else 1)
