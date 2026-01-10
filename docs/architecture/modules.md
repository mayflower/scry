# Module Structure

## Directory Layout

```
src/scry/
├── api/                    # REST endpoints
│   ├── routes.py           # API route definitions
│   └── dto.py              # Request/response models
├── core/                   # Core business logic
│   ├── ir/
│   │   └── model.py        # ScrapePlan IR definitions
│   ├── nav/
│   │   ├── explore.py      # Exploration data model
│   │   └── navigator.py    # IR execution engine
│   ├── extractor/
│   │   ├── extract.py      # Data extraction
│   │   ├── llm_extract.py  # LLM-driven extraction
│   │   └── selector_plan.py # Selector optimization
│   ├── optimizer/
│   │   ├── optimize.py     # Path compression
│   │   └── selectors.py    # Selector stabilization
│   ├── codegen/
│   │   └── generator.py    # Playwright script generation
│   ├── executor/
│   │   └── runner.py       # Script execution
│   ├── validator/
│   │   └── validate.py     # JSON schema validation
│   └── self_heal/
│       ├── diagnose.py     # Failure diagnosis
│       └── patch.py        # Heuristic patches
├── adapters/               # External integrations
│   ├── playwright_explorer.py  # LLM-driven exploration
│   ├── playwright.py       # Low-level Playwright helpers
│   ├── anthropic.py        # Claude API wrapper
│   └── browser_pool.py     # Async browser pool
├── runtime/                # Runtime services
│   ├── events.py           # Event bus (Redis/in-memory)
│   └── storage.py          # Artifact storage
├── config/
│   └── settings.py         # Environment configuration
├── app.py                  # FastAPI application factory
├── worker.py               # Async job processor
└── mcp_server.py           # MCP server for LLM integration
```

## Layer Responsibilities

### API Layer (`api/`)

Handles HTTP requests and responses:

- `routes.py` - REST endpoints (POST /scrape, /scrape/async, GET /jobs/{id})
- `dto.py` - Pydantic models for request/response validation

### Core Layer (`core/`)

Contains all business logic:

- **IR**: Intermediate representation for scraping plans
- **Navigation**: Exploration and execution engines
- **Extraction**: Data extraction from pages
- **Optimization**: Path and selector optimization
- **Code Generation**: Playwright script generation
- **Execution**: Script running and artifact capture
- **Validation**: Schema validation
- **Self-Healing**: Failure diagnosis and patching

### Adapters Layer (`adapters/`)

External integrations:

- **Playwright**: Browser automation
- **Anthropic**: Claude LLM API
- **Browser Pool**: Pre-launched browser management

### Runtime Layer (`runtime/`)

Infrastructure services:

- **Events**: Event bus for job processing (Redis or in-memory)
- **Storage**: Artifact I/O (screenshots, generated code, HTML)

## Key Files

| File | Purpose |
|------|---------|
| `playwright_explorer.py` | Main exploration engine |
| `ir/model.py` | ScrapePlan IR definitions |
| `codegen/generator.py` | Script generation |
| `executor/runner.py` | Script execution |
| `self_heal/diagnose.py` | Failure analysis |
