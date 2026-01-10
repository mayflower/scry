# Quick Start

## Basic Usage

Send a scrape request to extract data from a webpage:

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

## Request Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `nl_request` | string | Natural language description of what to extract |
| `output_schema` | object | JSON schema describing expected output structure |
| `target_urls` | array | List of URLs to scrape |
| `login_params` | object | Optional credentials for authentication |

## Response

```json
{
  "job_id": "abc123",
  "data": {
    "title": "Product Name",
    "price": 29.99,
    "description": "Product description..."
  },
  "execution_log": ["received", "exploring", "exploration_complete", "codegen", "executing_script", "done"],
  "status": "success"
}
```

## What Happens

1. **Exploration**: The LLM analyzes the page and decides navigation actions
2. **IR Generation**: Actions are compiled into a ScrapePlan intermediate representation
3. **Code Generation**: A pure Playwright Python script is generated
4. **Execution**: The script runs and extracts data
5. **Self-Healing**: On failure, the system diagnoses and retries with patches

## Artifacts

After a successful scrape, artifacts are stored in `artifacts/`:

- `screenshots/{job_id}/step-*.png` - Step-by-step screenshots
- `generated_code/{job_id}.py` - Pure Playwright script
- `html/{job_id}-page-*.html` - HTML snapshots

## Next Steps

- [Authentication](../api/authentication.md) - Scrape authenticated pages
- [API Endpoints](../api/endpoints.md) - Full API reference
