# Installation

## Prerequisites

- Python 3.12+
- Anthropic API key

## Local Installation

```bash
# Install package
pip install -e .

# Install Playwright browsers
python -m playwright install chromium
```

## Environment Setup

Set your Anthropic API key:

```bash
export ANTHROPIC_API_KEY=your_key_here
```

Or create a `.env` file:

```
ANTHROPIC_API_KEY=your_key_here
```

## Start the API Server

```bash
uvicorn scry.app:create_app --factory --host 0.0.0.0 --port 8000
```

## Verify Installation

```bash
curl http://localhost:8000/healthz
```

You should receive a successful health check response.

## Next Steps

- [Quick Start](quick-start.md) - Run your first scrape
- [Docker Setup](docker.md) - Deploy with Docker Compose
