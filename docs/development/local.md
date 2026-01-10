# Local Development

## Setup

### Install Dependencies

```bash
# Install package in editable mode
pip install -e .

# Install browser-use for exploration
pip install browser-use

# Install Playwright browsers
python -m playwright install chromium
```

### Start the API Server

```bash
uvicorn scry.app:create_app --factory --host 0.0.0.0 --port 8000
```

### Verify Setup

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

## Development Workflow

### Code Changes

1. Make changes to source files in `src/scry/`
2. The editable install (`pip install -e .`) means changes are reflected immediately
3. Restart the uvicorn server to pick up changes

### Running Locally vs Docker

| Aspect | Local | Docker |
|--------|-------|--------|
| Event backend | `inmemory` | `redis` |
| Artifacts path | `./artifacts` | `/app/artifacts` |
| Best for | Development | Production |

Set `EVENT_BACKEND=inmemory` for local development without Redis:

```bash
EVENT_BACKEND=inmemory uvicorn scry.app:create_app --factory
```

## Debugging

### Enable Debug Logging

```bash
export HEADLESS=false  # See browser actions
```

### Inspect Artifacts

After a scrape, check:

- `artifacts/screenshots/` - Step-by-step screenshots
- `artifacts/generated_code/` - Generated Playwright scripts
- `artifacts/html/` - HTML snapshots

### Test Generated Scripts Manually

```bash
# Run a generated script directly
python artifacts/generated_code/{job_id}.py
```

## Code Quality

### Pre-commit Hooks

The project uses pre-commit hooks for:

- `ruff` - Linting and formatting
- `mypy` - Type checking
- `bandit` - Security checks

### Run Checks Manually

```bash
# Format
ruff format src/

# Lint
ruff check src/

# Type check
mypy src/

# Security check
bandit -r src/
```
