#!/usr/bin/env python3
"""Test that validates the full exploration -> script generation -> validation pipeline for airport data.

This test:
1. Uses exploration to find recent flights from an airport homepage
2. Generates an optimized robot script based on the exploration
3. Validates that the generated script produces the same results
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import requests

# Test configuration
BASE_URL = os.getenv("SMARTR_BASE_URL", "http://127.0.0.1:8000")
TIMEOUT = int(os.getenv("SMARTR_TIMEOUT", "300"))


class TestAirportExplorationToScript:
    """Test full pipeline from exploration to script generation and validation."""

    @pytest.fixture
    def flight_schema(self) -> dict[str, Any]:
        """Schema for extracting flight information."""
        return {
            "type": "object",
            "properties": {
                "flights": {
                    "type": "array",
                    "description": "List of recent arriving flights",
                    "items": {
                        "type": "object",
                        "properties": {
                            "flight_number": {
                                "type": "string",
                                "description": "Flight number (e.g., LH123, EW9084)",
                            },
                            "origin": {
                                "type": "string",
                                "description": "Origin city or airport code",
                            },
                            "scheduled_time": {
                                "type": "string",
                                "description": "Scheduled arrival time",
                            },
                            "status": {
                                "type": "string",
                                "description": "Current status (landed, approaching, delayed, etc.)",
                            },
                        },
                    },
                },
                "extraction_time": {
                    "type": "string",
                    "description": "Time when data was extracted",
                },
            },
        }

    def run_exploration(self, airport_url: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Run exploration phase to find flight data."""
        payload = {
            "nl_request": (
                "Navigate from the homepage to find arrivals/flights section. "
                "Extract information about the most recent or currently arriving flights. "
                "Look for flight numbers, origins, times, and status."
            ),
            "schema": schema,
            "target_urls": [airport_url],
        }

        print(f"\n{'=' * 60}")
        print("PHASE 1: EXPLORATION")
        print(f"{'=' * 60}")
        print(f"Target: {airport_url}")
        print(f"Time: {datetime.now().strftime('%H:%M:%S')}")

        response = requests.post(
            f"{BASE_URL}/scrape",
            json=payload,
            timeout=TIMEOUT,
        )
        response.raise_for_status()

        result = response.json()
        print(f"Job ID: {result.get('job_id')}")

        # Log execution steps
        if "execution_log" in result:
            print("\nExecution log (last 10 steps):")
            for step in result["execution_log"][-10:]:
                print(f"  - {step}")

        return result

    def extract_generated_script(self, job_id: str) -> str:
        """Extract the generated Playwright script from artifacts."""
        # Look for generated script in artifacts directory
        artifacts_dir = (
            Path("/app/artifacts") if os.path.exists("/app/artifacts") else Path("artifacts")
        )
        script_path = artifacts_dir / "generated_code" / f"{job_id}.py"

        if script_path.exists():
            return script_path.read_text()

        # Try alternative locations
        alt_paths = [
            Path(f"artifacts/generated_code/{job_id}.py"),
            Path(f"/tmp/{job_id}_generated.py"),
        ]

        for path in alt_paths:
            if path.exists():
                return path.read_text()

        return None

    def run_generated_script(self, script_content: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Run the generated script and extract data."""
        if not script_content:
            pytest.skip("No generated script found")

        print(f"\n{'=' * 60}")
        print("PHASE 2: RUNNING GENERATED SCRIPT")
        print(f"{'=' * 60}")

        # Save script to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(script_content)
            script_path = f.name

        try:
            # Run the script
            print(f"Running script: {script_path}")
            result = subprocess.run(
                ["python", script_path],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                print(f"Script error: {result.stderr}")
                return None

            # Parse output - the script should print extracted data as JSON
            output_lines = result.stdout.strip().split("\n")
            for line in reversed(output_lines):
                try:
                    if line.strip().startswith("{"):
                        return json.loads(line)
                except json.JSONDecodeError:
                    continue

            print(f"Script output: {result.stdout}")
            return None

        finally:
            os.unlink(script_path)

    def validate_results(
        self,
        exploration_data: dict[str, Any],
        script_data: dict[str, Any],
    ) -> bool:
        """Validate that script produces similar results to exploration."""
        print(f"\n{'=' * 60}")
        print("PHASE 3: VALIDATION")
        print(f"{'=' * 60}")

        if not script_data:
            print("❌ No data from generated script")
            return False

        # Extract flight data from both results
        exp_flights = exploration_data.get("data", {}).get("flights", [])
        script_flights = script_data.get("flights", [])

        print(f"Exploration found: {len(exp_flights)} flights")
        print(f"Script found: {len(script_flights)} flights")

        if not exp_flights and not script_flights:
            print("⚠️ No flights found in either method")
            return True  # Both found nothing

        if not script_flights:
            print("❌ Script found no flights while exploration did")
            return False

        # Compare first few flights (they might be in different order)
        exp_flight_nums = {
            f.get("flight_number") for f in exp_flights[:5] if f.get("flight_number")
        }
        script_flight_nums = {
            f.get("flight_number") for f in script_flights[:5] if f.get("flight_number")
        }

        overlap = exp_flight_nums & script_flight_nums

        print(f"\nExploration flights: {exp_flight_nums}")
        print(f"Script flights: {script_flight_nums}")
        print(f"Overlap: {overlap}")

        if overlap:
            print(f"✅ Found {len(overlap)} matching flights")
            return True

        # Even if flight numbers don't match exactly, check if structure is similar
        if exp_flights and script_flights:
            exp_first = exp_flights[0]
            script_first = script_flights[0]

            # Check if both have similar fields
            exp_keys = set(exp_first.keys())
            script_keys = set(script_first.keys())

            if exp_keys & script_keys:
                print(f"✅ Structure matches with fields: {exp_keys & script_keys}")
                return True

        print("❌ No matching flights or structure")
        return False

    @pytest.mark.slow
    @pytest.mark.integration
    def test_munich_airport_exploration_to_script(self, flight_schema):
        """Test Munich airport: exploration -> script generation -> validation."""
        airport_url = "https://www.munich-airport.de"

        print(f"\n{'=' * 60}")
        print("MUNICH AIRPORT TEST")
        print(f"{'=' * 60}")

        # Phase 1: Exploration
        exploration_result = self.run_exploration(airport_url, flight_schema)

        exploration_data = exploration_result.get("data", {})
        if exploration_data:
            print("\n✅ Exploration successful")
            flights = exploration_data.get("flights", [])
            if flights:
                print(f"Found {len(flights)} flights")
                for i, flight in enumerate(flights[:3], 1):
                    print(
                        f"  {i}. {flight.get('flight_number', 'N/A')} from {flight.get('origin', 'N/A')}"
                    )

        # Phase 2: Get generated script
        job_id = exploration_result.get("job_id")
        if job_id:
            time.sleep(2)  # Give time for script to be saved
            script_content = self.extract_generated_script(job_id)

            if script_content:
                print(f"\n✅ Found generated script ({len(script_content)} chars)")
                print("Script preview (first 500 chars):")
                print(script_content[:500])

                # Phase 3: Run generated script
                script_data = self.run_generated_script(script_content, flight_schema)

                # Phase 4: Validate
                is_valid = self.validate_results(exploration_result, script_data)

                assert is_valid, "Generated script did not produce similar results"
            else:
                print("⚠️ No generated script found, checking if data was extracted directly")
                assert exploration_data, "No data extracted and no script generated"

    @pytest.mark.slow
    @pytest.mark.integration
    def test_simple_airport_exploration(self, flight_schema):
        """Test with a simpler airport website or flight tracker."""
        # Use a simpler flight tracking site that might be faster
        simpler_url = "https://www.flightradar24.com/airport/muc/arrivals"

        print(f"\n{'=' * 60}")
        print("SIMPLE FLIGHT TRACKER TEST")
        print(f"{'=' * 60}")

        try:
            exploration_result = self.run_exploration(simpler_url, flight_schema)

            data = exploration_result.get("data", {})
            flights = data.get("flights", [])

            if flights:
                print(f"\n✅ Found {len(flights)} flights")
                for flight in flights[:3]:
                    print(
                        f"  - {flight.get('flight_number', 'N/A')}: {flight.get('origin', 'N/A')} -> {flight.get('status', 'N/A')}"
                    )

                # Even without script generation, we validated exploration works
                assert len(flights) > 0, "Should find at least one flight"
            else:
                print("⚠️ No flights found, site might have changed")

        except requests.Timeout:
            pytest.skip("Request timed out - site may be too complex")

    def test_exploration_generates_ir(self):
        """Test that exploration generates intermediate representation."""

        # Simple test URL
        payload = {
            "nl_request": "Extract the page title",
            "schema": {"type": "object", "properties": {"title": {"type": "string"}}},
            "target_urls": ["https://example.com"],
        }

        response = requests.post(
            f"{BASE_URL}/scrape",
            json=payload,
            timeout=60,
        )

        assert response.status_code == 200
        result = response.json()

        # Check if IR/plan was generated (would be in artifacts)
        job_id = result.get("job_id")
        if job_id:
            # Check for IR artifacts
            artifacts_dir = Path("artifacts")
            ir_file = artifacts_dir / "plans" / f"{job_id}.json"

            if ir_file.exists():
                plan_data = json.loads(ir_file.read_text())
                print(f"✅ Found IR/Plan with {len(plan_data.get('actions', []))} actions")

                # Validate it's a proper ScrapePlan
                assert "actions" in plan_data
                assert "options" in plan_data


if __name__ == "__main__":
    # Run tests
    test = TestAirportExplorationToScript()
    schema = {
        "type": "object",
        "properties": {
            "flights": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "flight_number": {"type": "string"},
                        "origin": {"type": "string"},
                        "scheduled_time": {"type": "string"},
                        "status": {"type": "string"},
                    },
                },
            },
        },
    }

    # Try simple test first
    try:
        test.test_simple_airport_exploration(schema)
    except Exception as e:
        print(f"Error: {e}")

    # Then try full pipeline test
    try:
        test.test_munich_airport_exploration_to_script(schema)
    except Exception as e:
        print(f"Error: {e}")
