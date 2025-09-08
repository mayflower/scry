# Universal Scraper (V4: Self-Healing)

This implements V4 from plan.md. The API now performs agentic exploration plus a minimal self-healing loop:
- On script failure, it heuristically proposes a small patch (e.g., wait for load state, extra waits, generic cookie banner dismissal), regenerates the script, and retries.
- Stops after `MAX_REPAIR_ATTEMPTS` (default 20). Only the final script is kept.

Exploration uses Browser-Use to discover a path; then Anthropic compresses the trace to a short deterministic plan → codegen → execute (no AI at runtime). Compose includes `redis` and a `worker` process for async mode.

## Run locally (single process)

- Install: `pip install -e .`
- Install browsers: `python -m playwright install chromium`
- Install agent backend: `pip install browser-use` (and its dependencies)
- Start API: `uvicorn universal_scraper.app:create_app --factory --host 0.0.0.0 --port 8000`
- Health: `curl http://localhost:8000/healthz`
- Sample request:

```
curl -X POST http://localhost:8000/scrape \
  -H 'Content-Type: application/json' \
  -d '{
    "nl_request": "Open and extract basic info",
    "schema": {
      "type": "object",
      "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "links": {"type": "array", "items": {"type": "string"}}
      }
    },
    "target_urls": ["https://example.com"]
  }'
```

Artifacts:
- Screenshots: `artifacts/screenshots/{job_id}/step-*.png`
- HTML snapshot: `artifacts/html/{job_id}-page-1.html`
- Generated code: `artifacts/generated_code/{job_id}.py`

## Docker (V3 api + worker + redis)

Use Compose (recommended):

```
cd docker/compose
docker compose up --build
```

This starts:
- `redis` (queue), `api` (FastAPI), `worker` (job executor). Artifacts volume is shared.

## Environment

- `ANTHROPIC_API_KEY` (preferred) or `CLAUDE_API_KEY`
- `HEADLESS` default `true`
- `NAV_BACKEND` default `browser_use` (agentic exploration), `playwright` for deterministic replay
- `ARTIFACTS_ROOT` default `artifacts`
- `SCREENSHOT_DIR`, `GENERATED_CODE_DIR`, `HTML_SNAPSHOTS_DIR` derived from `ARTIFACTS_ROOT`
- `EXPLORATION_MODE` default `agentic`

## Notes

- Planning optimization is a no-op; structure is in place for selector stabilization.
- Self-heal is heuristic and domain-agnostic; no external logs are persisted.
- Exploration requires Browser-Use; there is no fallback to a custom explorer. Generated scripts do not embed secrets and only capture screenshots and the first page HTML.
