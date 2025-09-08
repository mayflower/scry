.PHONY: help up down build test test-integration test-all logs clean

help:
	@echo "Available commands:"
	@echo "  make up               - Start Docker Compose stack"
	@echo "  make down             - Stop Docker Compose stack"
	@echo "  make build            - Build Docker images"
	@echo "  make test             - Run quick validation test"
	@echo "  make test-integration - Run integration tests"
	@echo "  make test-all         - Run all tests"
	@echo "  make logs             - Show container logs"
	@echo "  make clean            - Clean up artifacts and containers"

up:
	cd docker/compose && docker compose up -d
	@echo "Waiting for services to be ready..."
	@sleep 5
	@docker compose -f docker/compose/docker-compose.yml exec api curl -sf http://localhost:8000/healthz && echo "API is ready" || echo "API not ready yet"

down:
	cd docker/compose && docker compose down

build:
	cd docker/compose && docker compose build

test: up
	@echo "Running quick validation test..."
	docker compose -f docker/compose/docker-compose.yml exec api python scripts/one_shot_free_places.py

test-integration: up
	@echo "Running integration tests..."
	docker compose -f docker/compose/docker-compose.yml exec api python scripts/test_munich_airport.py

test-all: up
	@echo "Running all tests..."
	docker compose -f docker/compose/docker-compose.yml exec api python scripts/test_smartscraper.py
	docker compose -f docker/compose/docker-compose.yml exec api python scripts/test_munich_airport.py

logs:
	cd docker/compose && docker compose logs -f

clean:
	cd docker/compose && docker compose down -v
	rm -rf artifacts/screenshots/*
	rm -rf artifacts/generated_code/*
	rm -rf artifacts/html/*
	@echo "Cleaned up containers and artifacts"