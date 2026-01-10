# Docker Setup

## Docker Compose

The recommended way to run Scry in production is with Docker Compose.

### Start the Stack

```bash
cd docker/compose
docker compose up --build
```

This starts three services:

| Service | Description |
|---------|-------------|
| `redis` | Job queue for async processing |
| `api` | FastAPI server |
| `worker` | Async job processor |

### Configuration

Create a `.env` file in `docker/compose/` with:

```
ANTHROPIC_API_KEY=your_key_here
```

### Makefile Commands

For convenience, use the Makefile:

```bash
make up      # Start services
make build   # Rebuild images
make down    # Stop services
make test    # Quick validation test
make logs    # Show container logs
make shell   # Shell in API container
```

## Running Tests in Docker

```bash
# Run all tests
docker compose exec worker pytest tests/ -v

# Run specific test file
docker compose exec worker pytest tests/test_browser_use_multi_step.py -v

# Skip slow tests
docker compose exec worker pytest -m "not slow" -v

# Run V2 tests only
docker compose exec worker pytest -m v2 -v
```

## Important Notes

!!! warning "Rebuild After Code Changes"
    Always rebuild Docker images after code changes. Never mount and manipulate code in volume.

```bash
docker compose up --build
```

## Verifying the Setup

```bash
# Health check
curl http://localhost:8000/healthz

# Test scrape
curl -X POST http://localhost:8000/scrape \
  -H 'Content-Type: application/json' \
  -d '{
    "nl_request": "Extract title",
    "output_schema": {"type": "object", "properties": {"title": {"type": "string"}}},
    "target_urls": ["https://example.com"]
  }'
```
