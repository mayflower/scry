#!/bin/bash
# Run tests in Docker environment

set -e

echo "Running V2 tests in Docker..."

# Install test dependencies if needed
docker compose exec -T worker pip install pytest >/dev/null 2>&1 || true

# Run V2 tests
echo "Testing V2 flow..."
docker compose exec -T worker python -m pytest tests/test_v2_flow.py -xvs --tb=short

echo "All V2 tests completed in Docker"