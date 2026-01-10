# Environment Variables

## Required

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude |
| `CLAUDE_API_KEY` | Alternative name for API key (fallback) |

## General Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `NAV_BACKEND` | `playwright` | Navigation backend (native agentic exploration) |
| `HEADLESS` | `true` | Run browser in headless mode |
| `EVENT_BACKEND` | `inmemory` | Event queue backend (`redis` or `inmemory`) |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection URL |
| `ARTIFACTS_ROOT` | `/app/artifacts` | Path for storing artifacts |
| `MAX_EXPLORATION_STEPS` | `20` | Maximum exploration steps |
| `MAX_REPAIR_ATTEMPTS` | `20` | Self-healing retry limit |

## MCP Server

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_PORT` | `8085` | Port for MCP server |
| `MCP_HOST` | `0.0.0.0` | Host to bind MCP server |

## Browser Pool

| Variable | Default | Description |
|----------|---------|-------------|
| `BROWSER_USE_POOL` | `true` | Enable browser pool |
| `BROWSER_POOL_SIZE` | `2` | Number of pre-launched browsers |
| `BROWSER_MAX_REQUESTS` | `100` | Recycle browser after N requests |
| `BROWSER_MAX_AGE` | `3600` | Recycle browser after N seconds |
| `BROWSER_HEALTH_CHECK_INTERVAL` | `60` | Health check interval in seconds |

## Configuration by Environment

### Local Development

```bash
export ANTHROPIC_API_KEY=your_key_here
export EVENT_BACKEND=inmemory
export HEADLESS=false  # See browser for debugging
```

### Docker Compose

Create `.env` in `docker/compose/`:

```
ANTHROPIC_API_KEY=your_key_here
EVENT_BACKEND=redis
REDIS_URL=redis://redis:6379/0
```

### Production

```bash
export ANTHROPIC_API_KEY=your_key_here
export EVENT_BACKEND=redis
export REDIS_URL=redis://your-redis-host:6379/0
export HEADLESS=true
export BROWSER_POOL_SIZE=4
export MAX_EXPLORATION_STEPS=30
```

## Loading Environment Variables

### From Shell

```bash
export ANTHROPIC_API_KEY=your_key_here
```

### From .env File

Create a `.env` file:

```
ANTHROPIC_API_KEY=your_key_here
EVENT_BACKEND=inmemory
```

The application loads `.env` automatically using python-dotenv.

### In Docker Compose

Pass via `environment` in `docker-compose.yml` or use `env_file`:

```yaml
services:
  api:
    env_file:
      - .env
    environment:
      - EVENT_BACKEND=redis
```
