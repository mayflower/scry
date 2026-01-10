# API Endpoints

## POST /scrape

Synchronous scraping request. Blocks until completion.

### Request

```json
{
  "nl_request": "Extract product information",
  "output_schema": {
    "type": "object",
    "properties": {
      "title": {"type": "string"},
      "price": {"type": "number"}
    }
  },
  "target_urls": ["https://example.com/product"],
  "login_params": {
    "username": "user@example.com",
    "password": "secret123"
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `nl_request` | string | Yes | Natural language description of the task |
| `output_schema` | object | Yes | JSON schema for expected output |
| `target_urls` | array | Yes | URLs to scrape |
| `login_params` | object | No | Login credentials (username, password) |

### Response

```json
{
  "job_id": "abc123",
  "data": {
    "title": "Product Name",
    "price": 29.99
  },
  "execution_log": ["received", "exploring", "exploration_complete", "codegen", "executing_script", "done"],
  "status": "success"
}
```

## POST /scrape/async

Asynchronous scraping request. Returns immediately with job ID.

### Request

Same as `/scrape`.

### Response

```json
{
  "job_id": "abc123",
  "status": "pending"
}
```

## GET /jobs/{job_id}

Poll job status and results.

### Response (Pending)

```json
{
  "job_id": "abc123",
  "status": "pending",
  "data": null
}
```

### Response (Completed)

```json
{
  "job_id": "abc123",
  "status": "success",
  "data": {
    "title": "Product Name",
    "price": 29.99
  },
  "execution_log": ["received", "exploring", "exploration_complete", "codegen", "executing_script", "done"]
}
```

### Response (Failed)

```json
{
  "job_id": "abc123",
  "status": "failed",
  "data": null,
  "execution_log": ["received", "exploring", "error: timeout"]
}
```

## GET /healthz

Health check endpoint.

### Response

```json
{
  "status": "healthy"
}
```

## GET /llm/ready

Readiness probe checking LLM availability.

### Response

```json
{
  "ready": true,
  "api_key_configured": true,
  "browser_available": true
}
```

## Error Responses

All endpoints return standard error responses:

```json
{
  "detail": "Error message describing the problem"
}
```

| Status Code | Description |
|-------------|-------------|
| 400 | Bad request (invalid parameters) |
| 404 | Job not found |
| 500 | Internal server error |
