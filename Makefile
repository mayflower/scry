.PHONY: help up down build test test-unit test-integration test-v1 test-v2 test-v3 test-all logs clean shell

help:
	@echo "Available commands:"
	@echo "  make up               - Start Docker Compose stack"
	@echo "  make down             - Stop Docker Compose stack"
	@echo "  make build            - Build Docker images"
	@echo "  make test             - Run quick validation test"
	@echo "  make test-unit        - Run all unit tests (V1, V2, V3) in Docker"
	@echo "  make test-v1          - Run V1 tests in Docker"
	@echo "  make test-v2          - Run V2 tests in Docker"
	@echo "  make test-v3          - Run V3 tests in Docker"
	@echo "  make test-integration - Run integration tests in Docker"
	@echo "  make test-all         - Run ALL tests in Docker"
	@echo "  make logs             - Show container logs"
	@echo "  make clean            - Clean up artifacts and containers"
	@echo "  make shell            - Open shell in API container"

up:
	cd docker/compose && docker compose up -d
	@echo "Waiting for services to be ready..."
	@sleep 5
	@cd docker/compose && docker compose exec api curl -sf http://localhost:8000/healthz && echo "API is ready" || echo "API not ready yet"

down:
	cd docker/compose && docker compose down

build:
	cd docker/compose && docker compose build

test: up
	@echo "Running quick validation test..."
	cd docker/compose && docker compose exec api python scripts/one_shot_free_places.py

test-unit: up
	@echo "Running all unit tests in Docker..."
	cd docker/compose && docker compose exec worker python -m pytest tests/ -v --tb=short

test-v1: up
	@echo "Running V1 tests in Docker..."
	cd docker/compose && docker compose exec worker python -m pytest tests/test_v1_minimal.py -v --tb=short

test-v2: up
	@echo "Running V2 tests in Docker..."
	@echo "Installing test dependencies..."
	@cd docker/compose && docker compose exec worker pip install pytest >/dev/null 2>&1 || true
	cd docker/compose && docker compose exec worker python -m pytest tests/test_v2_flow.py -v --tb=short

test-v3: up
	@echo "Running V3 tests in Docker..."
	cd docker/compose && docker compose exec worker python -m pytest tests/test_v3_codegen.py tests/test_v3_integration.py -v --tb=short

test-integration: up
	@echo "Running integration tests in Docker..."
	cd docker/compose && docker compose exec api python scripts/test_smartscraper.py
	cd docker/compose && docker compose exec api python scripts/test_munich_airport.py

test-all: up
	@echo "Running ALL tests in Docker..."
	@echo "Installing test dependencies..."
	@cd docker/compose && docker compose exec worker pip install pytest >/dev/null 2>&1 || true
	@echo "=== Unit Tests ==="
	cd docker/compose && docker compose exec worker python -m pytest tests/ -v --tb=short
	@echo "=== Integration Tests ==="
	cd docker/compose && docker compose exec api python scripts/test_smartscraper.py
	cd docker/compose && docker compose exec api python scripts/test_munich_airport.py

logs:
	cd docker/compose && docker compose logs -f

clean:
	cd docker/compose && docker compose down -v
	rm -rf artifacts/screenshots/*
	rm -rf artifacts/generated_code/*
	rm -rf artifacts/html/*
	@echo "Cleaned up containers and artifacts"

shell: up
	@echo "Opening shell in worker container..."
	cd docker/compose && docker compose exec worker /bin/bash