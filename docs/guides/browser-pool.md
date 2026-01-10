# Browser Pool

Scry includes an async browser pool that eliminates cold-start latency by pre-launching browsers.

## Performance Comparison

| Metric | Without Pool | With Pool |
|--------|-------------|-----------|
| First request | 3-5s | 0.3s (pool init) + 0.05s (acquire) |
| Subsequent requests | 3-5s | ~0.05s |

## How It Works

1. **Initialization**: On first request, the pool launches N browsers asynchronously (~0.3s)
2. **Acquisition**: Requests acquire a browser from the pool (~0.05s vs 3-5s cold start)
3. **Return**: After use, browsers return to the pool for reuse
4. **Health Checks**: Unhealthy browsers are automatically replaced
5. **Recycling**: Browsers are recycled after max requests or max age to prevent memory leaks

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `BROWSER_USE_POOL` | `true` | Enable/disable the pool |
| `BROWSER_POOL_SIZE` | `2` | Number of pre-launched browsers |
| `BROWSER_MAX_REQUESTS` | `100` | Recycle after N requests |
| `BROWSER_MAX_AGE` | `3600` | Recycle after N seconds |
| `BROWSER_HEALTH_CHECK_INTERVAL` | `60` | Health check interval in seconds |

## Usage

### Enable the Pool (Default)

```bash
export BROWSER_USE_POOL=true
export BROWSER_POOL_SIZE=2
```

### Disable the Pool

For debugging or resource-constrained environments:

```bash
export BROWSER_USE_POOL=false
```

### Production Settings

For high-throughput scenarios:

```bash
export BROWSER_USE_POOL=true
export BROWSER_POOL_SIZE=4
export BROWSER_MAX_REQUESTS=200
export BROWSER_MAX_AGE=7200
```

## Pool Lifecycle

### Startup

```
[Pool] Initializing pool with 2 browsers
[Pool] Browser 1 launched
[Pool] Browser 2 launched
[Pool] Pool ready (0.3s)
```

### Request Handling

```
[Pool] Acquiring browser (0.05s)
[Explorer] Starting exploration...
[Pool] Returning browser to pool
```

### Health Checks

```
[Pool] Health check started
[Pool] Browser 1: healthy
[Pool] Browser 2: unhealthy (stale)
[Pool] Replacing browser 2
[Pool] Browser 2 replaced
```

### Recycling

```
[Pool] Browser 1 reached max requests (100)
[Pool] Recycling browser 1
[Pool] Browser 1 replaced
```

## Tuning Recommendations

### Memory-Constrained

```bash
BROWSER_POOL_SIZE=1
BROWSER_MAX_REQUESTS=50
BROWSER_MAX_AGE=1800
```

### High Throughput

```bash
BROWSER_POOL_SIZE=4
BROWSER_MAX_REQUESTS=200
BROWSER_MAX_AGE=7200
BROWSER_HEALTH_CHECK_INTERVAL=30
```

### Debugging

```bash
BROWSER_USE_POOL=false
HEADLESS=false
```

## Troubleshooting

### Pool Not Initializing

Check that Playwright browsers are installed:

```bash
python -m playwright install chromium
```

### Browsers Becoming Stale

Reduce `BROWSER_MAX_AGE` or `BROWSER_MAX_REQUESTS`:

```bash
BROWSER_MAX_AGE=1800
BROWSER_MAX_REQUESTS=50
```

### High Memory Usage

Reduce pool size and increase recycling frequency:

```bash
BROWSER_POOL_SIZE=1
BROWSER_MAX_REQUESTS=25
```
