# Project Instructions

## General Rules

- If tests do not run, fix the underlying problem or the test. Do not simply ignore it.
- Never ignore issues because they existed before your changes.

## Running Tests

### Before Running Tests

1. **Always check if tests are already running:**
   ```bash
   ps aux | grep pytest | grep -v grep
   ```
2. **Never start new tests if tests are already running.** Wait for them to complete or explicitly kill them first.

### Running Tests Reliably

1. **Run tests synchronously (preferred):**
   ```bash
   uv run pytest tests/ -v --tb=short -m "not integration"
   ```
   This blocks until completion. Use appropriate timeout (tests can take several minutes).

2. **For quick verification, run specific test files:**
   ```bash
   uv run pytest tests/test_specific_file.py -v --tb=short
   ```

3. **If you must run in background:**
   - Use `TaskOutput` with `block=true` and `timeout=600000` (10 minutes)
   - Do NOT use `tail` to check progress and then assume tests are stuck
   - Wait for the full result before taking any action

### Integration Tests

Tests marked with `@pytest.mark.integration` require external services (Redis, etc.) and may make real API calls.

**Important:**
- These tests are NOT stuck just because output stops for a few minutes
- A single LLM test can take 1-3 minutes waiting for API responses
- Do NOT kill these tests prematurely
- If you need quick verification, exclude them with `-m "not integration"`

## Pre-commit Checks

Before committing, always run:
```bash
uv run ruff check src/scry tests/
uv run ruff format --check src/scry tests/
uv run mypy src/scry
```

## SonarQube Integration

This project uses SonarQube for code quality analysis. The following Claude skills are available:

### `/sonar-status`
Check the current quality gate status and code metrics from SonarQube.

### `/sonar-fix`
Find and fix SonarQube issues, prioritized by severity (BLOCKER -> CRITICAL -> HIGH -> etc.).

### `/pr-quality`
Create a pull request with embedded quality metrics and CI status checks.

### `/push-watch`
Push the current branch and monitor the CI workflow until completion.

## CI Pipeline

The CI workflow consists of 3 jobs:

1. **Quality Checks** (ubuntu-latest)
   - Ruff linting with SARIF output
   - Ruff format check
   - Mypy type checking with SARIF output
   - Bandit security scanning

2. **Tests** (ubuntu-latest)
   - pytest with coverage and JUnit XML output

3. **SonarQube Analysis** (mayflower-k8s-runners)
   - Downloads artifacts from quality and test jobs
   - Sends all reports to SonarQube
