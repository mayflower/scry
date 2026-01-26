.PHONY: help install lint lint-fix format format-fix typecheck security quality test-local coverage up down build test test-unit test-integration test-v1 test-v2 test-v3 test-all logs clean shell

help:
	@echo "Local Development (uv):"
	@echo "  make install          - Install dependencies with uv"
	@echo "  make lint             - Run ruff linter"
	@echo "  make lint-fix         - Run ruff linter and auto-fix issues"
	@echo "  make format           - Check code formatting with ruff"
	@echo "  make format-fix       - Auto-format code with ruff"
	@echo "  make typecheck        - Run mypy type checker"
	@echo "  make security         - Run bandit security scanner"
	@echo "  make quality          - Run all quality checks (lint, format, typecheck, security)"
	@echo "  make test-local       - Run tests locally with pytest"
	@echo "  make coverage         - Run tests with coverage report"
	@echo ""
	@echo "Docker Commands:"
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

# =============================================================================
# Local Development (uv)
# =============================================================================

install:
	uv sync --extra dev

lint:
	uv run ruff check src/scry tests/

lint-fix:
	uv run ruff check src/scry tests/ --fix

format:
	uv run ruff format --check src/scry tests/

format-fix:
	uv run ruff format src/scry tests/

typecheck:
	uv run mypy src/scry

security:
	uv run bandit -r src/scry -f json -o bandit-results.json || true
	@echo "Bandit results written to bandit-results.json"

quality: lint format typecheck security
	@echo "All quality checks passed!"

test-local:
	uv run pytest tests/ -v --tb=short -m "not integration"

coverage:
	uv run pytest tests/ -v -m "not integration" \
		--cov=src/scry \
		--cov-report=term-missing \
		--cov-report=xml:coverage.xml \
		--junitxml=junit.xml

# =============================================================================
# Docker Commands
# =============================================================================

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