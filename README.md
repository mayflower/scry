# Scry - Agentic Web Scraper

**Scry** (from "scrying" - the practice of seeing hidden information) is an intelligent web scraper with LLM-driven exploration and self-healing capabilities.

## Features

- **Agentic Exploration**: LLM-driven navigation using Anthropic Claude + Playwright
- **Complete Action Vocabulary**: Navigate, Click, Fill, Select (dropdowns), Hover (hover effects), KeyPress (keyboard events), Upload (file uploads), WaitFor, Validate
- **LLM-Driven Authentication**: Automatic login form detection and filling using credentials from `login_params`
- **Self-Healing**: Automatic retry with intelligent patches on failure (up to 20 repair attempts)
- **IR-Based Architecture**: Exploration → ScrapePlan IR → Optimization → Code generation → Execution
- **No AI at Runtime**: Generated scripts are pure Playwright Python with no embedded secrets
- **Event-Driven**: Redis-based async job processing

## Quick Start

### Local Installation

```bash
# Install package
pip install -e .

# Install Playwright browsers
python -m playwright install chromium

# Start API server
uvicorn scry.app:create_app --factory --host 0.0.0.0 --port 8000

# Health check
curl http://localhost:8000/healthz
```

### Basic Usage

```bash
curl -X POST http://localhost:8000/scrape \
  -H 'Content-Type: application/json' \
  -d '{
    "nl_request": "Extract product information",
    "output_schema": {
      "type": "object",
      "properties": {
        "title": {"type": "string"},
        "price": {"type": "number"},
        "description": {"type": "string"}
      }
    },
    "target_urls": ["https://example-shop.com/product"]
  }'
```

### With Authentication

```bash
curl -X POST http://localhost:8000/scrape \
  -H 'Content-Type: application/json' \
  -d '{
    "nl_request": "Extract my recent orders",
    "output_schema": {
      "type": "object",
      "properties": {
        "orders": {"type": "array", "items": {"type": "string"}}
      }
    },
    "target_urls": ["https://example-shop.com"],
    "login_params": {
      "username": "user@example.com",
      "password": "secret123"
    }
  }'
```

The LLM will automatically:
1. Detect login forms by analyzing page elements
2. Fill credentials using the provided username/password
3. Submit the form
4. Proceed with the main task after authentication

## Docker Compose Setup

```bash
cd docker/compose
docker compose up --build
```

This starts:
- `redis` - Job queue
- `api` - FastAPI server
- `worker` - Async job processor

Create a `.env` file in `docker/compose/` with:
```
ANTHROPIC_API_KEY=your_key_here
```

## Environment Variables

**Required:**
- `ANTHROPIC_API_KEY` or `CLAUDE_API_KEY`

**Optional:**
- `NAV_BACKEND`: `playwright` (native agentic exploration, default)
- `HEADLESS`: `true` (default)
- `EVENT_BACKEND`: `redis` (for Docker) or `inmemory` (local)
- `REDIS_URL`: `redis://redis:6379/0`
- `ARTIFACTS_ROOT`: `/app/artifacts`
- `MAX_EXPLORATION_STEPS`: Max exploration steps (default 20)
- `MAX_REPAIR_ATTEMPTS`: Self-healing retry limit (default 20)

## Artifacts

Generated artifacts are stored in `artifacts/`:
- **Screenshots**: `screenshots/{job_id}/step-*.png` - Step-by-step screenshots
- **Generated Code**: `generated_code/{job_id}.py` - Pure Playwright Python scripts
- **HTML Snapshots**: `html/{job_id}-page-*.html` - HTML snapshots for diagnosis

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run only unit tests
pytest tests/ -v -m "not integration"

# Run integration tests (requires ANTHROPIC_API_KEY)
pytest tests/ -v -m integration

# Run specific test suites
pytest tests/test_data_extraction.py -v
pytest tests/test_api_routes.py -v
pytest tests/test_new_actions.py -v
```

## Architecture

See [CLAUDE.md](CLAUDE.md) for detailed architecture documentation.

### System Flow

```mermaid
graph TB
    A[User Request] --> B[LLM-Driven Exploration]
    B --> C[ScrapePlan IR]
    C --> D[Optimization]
    D --> E[Code Generation]
    E --> F[Pure Playwright Script]
    F --> G{Execution Success?}
    G -->|Yes| H[Return Data + Artifacts]
    G -->|No| I[Self-Healing Diagnosis]
    I --> J[Apply Heuristic Patches]
    J --> K{Max Attempts?}
    K -->|No| D
    K -->|Yes| L[Return Failure]

    style B fill:#e1f5ff
    style F fill:#fff4e1
    style I fill:#ffe1e1
    style H fill:#e1ffe1
```

**Key Phases:**

1. **LLM-Driven Exploration** (adapters/playwright_explorer.py)
   - Claude analyzes page state and decides actions
   - Captures screenshots, HTML, URLs at each step
   - Outputs: ExplorationResult with navigation steps

2. **IR Compression** (core/ir/model.py)
   - Converts exploration into ScrapePlan IR
   - Actions: Navigate, Click, Fill, Select, Hover, KeyPress, Upload, WaitFor, Validate

3. **Optimization** (core/optimizer/optimize.py)
   - Compresses redundant paths
   - Stabilizes selectors with fallbacks

4. **Code Generation** (core/codegen/generator.py)
   - Generates pure Playwright Python script
   - No AI dependencies at runtime
   - No embedded secrets

5. **Execution** (core/executor/runner.py)
   - Runs generated script in isolated subprocess
   - Captures artifacts (screenshots, HTML)
   - Returns structured data

6. **Self-Healing** (core/self_heal/)
   - On failure: diagnose with HTML snapshots
   - Apply heuristic patches: wait_load_state, extra_wait_ms, handle_cookie_banner, etc.
   - Regenerate and retry (up to 20 attempts)

**Key Components:**
- `src/scry/api/` - REST endpoints
- `src/scry/core/` - Core business logic (IR, nav, extraction, optimization, codegen, execution, validation, self-healing)
- `src/scry/adapters/` - External integrations (Playwright, Anthropic Claude)
- `src/scry/runtime/` - Event bus and storage
- `src/scry/worker.py` - Async job processor

## License

MIT
