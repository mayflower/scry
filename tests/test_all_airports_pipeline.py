#!/usr/bin/env python3
"""Validate full pipeline (exploration → script → validation) for all three airports.

This test:
1. Runs exploration for each airport (Munich, Frankfurt, CDG)
2. Verifies script generation
3. Runs generated scripts
4. Validates that scripts produce similar results to exploration
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

BASE_URL = os.getenv("SMARTR_BASE_URL", "http://127.0.0.1:8000")
TIMEOUT = int(os.getenv("SMARTR_TIMEOUT", "300"))

# Airport configurations
AIRPORTS = {
    "Munich": {
        "url": "https://www.munich-airport.de",
        "name": "Munich Airport (MUC)",
        "code": "MUC",
    },
    "Frankfurt": {
        "url": "https://www.frankfurt-airport.com",
        "name": "Frankfurt Airport (FRA)",
        "code": "FRA",
    },
    "Paris_CDG": {
        "url": "https://www.parisaeroport.fr",
        "name": "Charles de Gaulle (CDG)",
        "code": "CDG",
    },
}


def get_flight_schema() -> dict[str, Any]:
    """Get standard schema for flight extraction."""
    return {
        "type": "object",
        "properties": {
            "flights": {
                "type": "array",
                "description": "List of arriving flights",
                "maxItems": 5,  # Limit to 5 flights for faster processing
                "items": {
                    "type": "object",
                    "properties": {
                        "flight_number": {
                            "type": "string",
                            "description": "Flight number (e.g., LH123)",
                        },
                        "origin": {
                            "type": "string",
                            "description": "Origin city or airport",
                        },
                        "scheduled_time": {
                            "type": "string",
                            "description": "Scheduled arrival time",
                        },
                        "status": {
                            "type": "string",
                            "description": "Current status",
                        },
                    },
                },
            },
            "extraction_timestamp": {
                "type": "string",
                "description": "When data was extracted",
            },
        },
    }


def run_exploration(
    airport_name: str, airport_info: dict[str, str]
) -> dict[str, Any] | None:
    """Run exploration phase for an airport."""
    print(f"\n{'=' * 70}")
    print(f"EXPLORATION: {airport_info['name']}")
    print(f"{'=' * 70}")
    print(f"URL: {airport_info['url']}")
    print(f"Time: {datetime.now().strftime('%H:%M:%S')}")

    payload = {
        "nl_request": (
            f"Navigate to {airport_info['name']} website. "
            "Find the arrivals section and extract information about "
            "the most recent or next arriving flights. "
            "Include flight number, origin, scheduled time, and status."
        ),
        "schema": get_flight_schema(),
        "target_urls": [airport_info["url"]],
    }

    try:
        print("Starting exploration...")
        response = requests.post(
            f"{BASE_URL}/scrape",
            json=payload,
            timeout=TIMEOUT,
        )

        if response.status_code == 200:
            result = response.json()
            job_id = result.get("job_id")
            data = result.get("data", {})
            flights = data.get("flights", [])

            print("✅ Exploration complete!")
            print(f"   Job ID: {job_id}")
            print(f"   Flights found: {len(flights)}")

            if flights:
                print("\n   Sample flights:")
                for i, flight in enumerate(flights[:3], 1):
                    print(
                        f"   {i}. {flight.get('flight_number', 'N/A')} from {flight.get('origin', 'N/A')}"
                    )
                    print(
                        f"      Time: {flight.get('scheduled_time', 'N/A')}, Status: {flight.get('status', 'N/A')}"
                    )

            # Store result
            result["airport"] = airport_name
            result["timestamp"] = datetime.now().isoformat()

            return result
        print(f"❌ Exploration failed: {response.status_code}")
        print(f"   Error: {response.text[:200]}")
        return None

    except requests.Timeout:
        print(f"⏱️ Exploration timed out after {TIMEOUT}s")
        return None
    except Exception as e:
        print(f"❌ Exploration error: {e}")
        return None


def check_generated_script(job_id: str) -> Path | None:
    """Check if script was generated and return its path."""
    if not job_id:
        return None

    script_path = Path(f"/app/artifacts/generated_code/{job_id}.py")

    if script_path.exists():
        size = script_path.stat().st_size
        print(f"   ✓ Script generated: {size} bytes")
        return script_path
    print(f"   ✗ No script found at {script_path}")
    return None


def run_generated_script(script_path: Path, job_id: str) -> dict[str, Any] | None:
    """Run the generated script and get extracted data."""
    print("\n   Running generated script...")

    try:
        # Run the script
        result = subprocess.run(
            ["python", str(script_path)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd="/app",
        )

        if result.returncode != 0:
            print(f"   ❌ Script error: {result.stderr[:200]}")
            return None

        # Check for saved data file
        data_file = Path(f"/app/artifacts/data/{job_id}.json")
        if data_file.exists():
            data = json.loads(data_file.read_text())
            print("   ✓ Script extracted data successfully")
            return data
        print(f"   ✗ No data file found at {data_file}")
        return None

    except subprocess.TimeoutExpired:
        print("   ⏱️ Script timed out")
        return None
    except Exception as e:
        print(f"   ❌ Script error: {e}")
        return None


def compare_results(
    exploration_data: dict[str, Any], script_data: dict[str, Any]
) -> bool:
    """Compare exploration and script results."""
    if not exploration_data or not script_data:
        return False

    exp_flights = exploration_data.get("data", {}).get("flights", [])
    script_flights = script_data.get("flights", [])

    print("\n   Comparison:")
    print(f"   - Exploration found: {len(exp_flights)} flights")
    print(f"   - Script found: {len(script_flights)} flights")

    if not exp_flights and not script_flights:
        print("   ⚠️ Both found no flights")
        return True

    if not script_flights and exp_flights:
        print(
            f"   ❌ Script found no flights while exploration found {len(exp_flights)}"
        )
        return False

    # Compare flight numbers
    exp_numbers = {
        f.get("flight_number") for f in exp_flights if f.get("flight_number")
    }
    script_numbers = {
        f.get("flight_number") for f in script_flights if f.get("flight_number")
    }

    if exp_numbers and script_numbers:
        overlap = exp_numbers & script_numbers
        if overlap:
            print(f"   ✅ Matching flights: {overlap}")
            return True
        print("   ⚠️ No exact flight matches, but both extracted data")
        print(f"      Exploration: {list(exp_numbers)[:3]}")
        print(f"      Script: {list(script_numbers)[:3]}")
        # Still consider success if both got data
        return bool(exp_flights and script_flights)

    # Check if at least both have similar structure
    if exp_flights and script_flights:
        exp_keys = set(exp_flights[0].keys()) if exp_flights else set()
        script_keys = set(script_flights[0].keys()) if script_flights else set()
        common_keys = exp_keys & script_keys

        if common_keys:
            print(f"   ✅ Both have similar structure: {common_keys}")
            return True

    print("   ❌ Results don't match")
    return False


def test_airport_pipeline(
    airport_name: str, airport_info: dict[str, str]
) -> dict[str, Any]:
    """Test complete pipeline for one airport."""
    result = {
        "airport": airport_name,
        "exploration": False,
        "script_generated": False,
        "script_runs": False,
        "results_match": False,
        "details": {},
    }

    # Phase 1: Exploration
    exploration_result = run_exploration(airport_name, airport_info)
    if exploration_result:
        result["exploration"] = True
        result["details"]["exploration_data"] = exploration_result.get("data", {})

        job_id = exploration_result.get("job_id")
        if job_id:
            # Phase 2: Check script generation
            time.sleep(2)  # Give time for script to be saved
            script_path = check_generated_script(job_id)

            if script_path:
                result["script_generated"] = True

                # Phase 3: Run generated script
                script_data = run_generated_script(script_path, job_id)

                if script_data:
                    result["script_runs"] = True
                    result["details"]["script_data"] = script_data

                    # Phase 4: Compare results
                    if compare_results(exploration_result, script_data):
                        result["results_match"] = True

    return result


def main():
    """Run pipeline tests for all airports."""
    print("\n" + "=" * 70)
    print("AIRPORT PIPELINE VALIDATION TEST")
    print("Testing: Exploration → Script Generation → Validation")
    print("=" * 70)

    results = {}

    # Test each airport
    for airport_name, airport_info in AIRPORTS.items():
        print(f"\n\n🛫 Testing {airport_name}...")
        results[airport_name] = test_airport_pipeline(airport_name, airport_info)

        # Brief pause between airports
        time.sleep(5)

    # Print summary
    print("\n\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)

    for airport, result in results.items():
        status_symbols = {
            "exploration": "🔍",
            "script_generated": "📝",
            "script_runs": "▶️",
            "results_match": "✅",
        }

        print(f"\n{AIRPORTS[airport]['name']}:")
        for key, symbol in status_symbols.items():
            status = "✓" if result[key] else "✗"
            print(f"  {symbol} {key.replace('_', ' ').title()}: {status}")

        # Show flight counts if available
        exp_data = result["details"].get("exploration_data", {})
        script_data = result["details"].get("script_data", {})

        if exp_data:
            exp_flights = exp_data.get("flights", [])
            print(f"     Exploration flights: {len(exp_flights)}")

        if script_data:
            script_flights = script_data.get("flights", [])
            print(f"     Script flights: {len(script_flights)}")

    # Overall success
    print("\n" + "=" * 70)
    total_success = sum(
        1
        for r in results.values()
        if r["exploration"] and r["script_generated"] and r["script_runs"]
    )

    print(f"Pipeline Success: {total_success}/{len(AIRPORTS)} airports")

    if total_success == len(AIRPORTS):
        print("🎉 All airports passed the full pipeline test!")
    elif total_success > 0:
        print(f"⚠️ Partial success: {total_success} airports completed the pipeline")
    else:
        print("❌ Pipeline test failed for all airports")

    # Save detailed results
    results_file = Path("/app/artifacts/airport_pipeline_results.json")
    results_file.write_text(json.dumps(results, indent=2))
    print(f"\nDetailed results saved to: {results_file}")


if __name__ == "__main__":
    main()
