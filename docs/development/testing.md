# Testing

## Running Tests

### Using Makefile (Recommended)

```bash
make test              # Quick validation
make test-unit         # All unit tests
make test-integration  # Integration tests
make test-all          # Everything
```

### Using pytest Directly

```bash
# Run all tests
pytest tests/ -v

# Run specific file
pytest tests/test_api_routes.py -v

# Run with markers
pytest -m integration -v
pytest -m "not slow" -v
```

### In Docker

```bash
cd docker/compose

# Run all tests
docker compose exec worker pytest tests/ -v

# Run specific test
docker compose exec worker pytest tests/test_browser_use_multi_step.py -v

# Skip slow tests
docker compose exec worker pytest -m "not slow" -v

# Run V2 tests only
docker compose exec worker pytest -m v2 -v
```

## Test Markers

Configure in `pytest.ini`:

| Marker | Description |
|--------|-------------|
| `v1` | V1 minimal tests |
| `v2` | V2 planning/exploration tests |
| `smoke` | Quick smoke tests |
| `e2e` | End-to-end tests |
| `integration` | Integration tests (require API key) |
| `slow` | Long-running tests |

### Using Markers

```bash
# Run only integration tests
pytest -m integration -v

# Exclude slow tests
pytest -m "not slow" -v

# Combine markers
pytest -m "v2 and not slow" -v
```

## Test Categories

### Unit Tests

Test individual components in isolation:

```bash
pytest tests/test_data_extraction.py -v
pytest tests/test_codegen.py -v
```

### Integration Tests

Test end-to-end flows (require `ANTHROPIC_API_KEY`):

```bash
pytest tests/ -v -m integration
```

### API Tests

Test REST endpoints:

```bash
pytest tests/test_api_routes.py -v
```

## Writing Tests

### Test File Structure

```python
import pytest

@pytest.mark.integration
def test_scrape_example_com():
    """Test scraping example.com."""
    # Test implementation
    pass

@pytest.mark.slow
def test_complex_navigation():
    """Test complex multi-step navigation."""
    # Long-running test
    pass
```

### Fixtures

Common fixtures are defined in `conftest.py`:

- `client` - FastAPI test client
- `mock_anthropic` - Mocked Anthropic API
- `temp_artifacts` - Temporary artifacts directory

## Continuous Integration

Tests run automatically on:

- Pull request creation
- Push to main branch

Integration tests require `ANTHROPIC_API_KEY` secret to be configured.
