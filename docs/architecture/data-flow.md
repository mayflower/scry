# Data Flow

The scraping pipeline consists of five main phases.

## Phase 1: Exploration

**File**: `adapters/playwright_explorer.py`

The LLM analyzes page state and decides actions:

1. Claude receives the current page state (elements, text, URL)
2. Based on the task description, it decides the next action
3. Actions are executed via Playwright
4. Screenshots, HTML, and URLs are captured at each step
5. Returns `ExplorationResult` with navigation steps

**Output**: `ExplorationResult` containing:

- Steps (Navigate, Click, Fill, etc.)
- Screenshots
- HTML snapshots
- Visited URLs

## Phase 2: Optimization

**File**: `core/optimizer/optimize.py`

Compresses exploration paths and stabilizes selectors:

- Removes redundant navigation steps
- Converts dynamic selectors to stable alternatives
- Adds fallback selectors for resilience

**Output**: Optimized `ScrapePlan` IR

## Phase 3: Code Generation

**File**: `core/codegen/generator.py`

Generates pure Playwright Python scripts:

- Converts IR actions to Playwright API calls
- Includes wait strategies and error handling
- No AI dependencies or secrets embedded

**Output**: Executable Python script (`artifacts/generated_code/{job_id}.py`)

## Phase 4: Execution

**File**: `core/executor/runner.py`

Runs generated scripts in isolated subprocess:

- Executes Playwright script
- Captures screenshots and HTML
- Extracts structured data
- Returns execution results

**Output**: Extracted data + artifacts

## Phase 5: Self-Healing

**Files**: `core/self_heal/diagnose.py`, `core/self_heal/patch.py`

On failure, diagnoses and patches:

1. Analyze HTML snapshots for failure cause
2. Propose heuristic patches:
   - `wait_load_state` - Wait for page load
   - `extra_wait_ms` - Add delay
   - `handle_cookie_banner` - Dismiss consent dialogs
3. Regenerate script with patches
4. Retry execution (up to 20 attempts)

**Output**: Either successful execution or failure after max attempts

## Action Types

The IR supports these action types:

| Action | Description |
|--------|-------------|
| `Navigate` | Go to URL |
| `Click` | Click element |
| `Fill` | Fill text input |
| `Select` | Select dropdown option |
| `Hover` | Hover over element |
| `KeyPress` | Press keyboard key |
| `Upload` | Upload file |
| `WaitFor` | Wait for condition |
| `Validate` | Validate element state |
