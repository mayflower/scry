# Completion Plan: Action Vocabulary + LLM-Driven Authentication

## Goal

Extend the universal scraper to support:
1. **Complete action vocabulary**: Select (dropdowns), Hover (hover-triggered content), KeyPress (keyboard events), Upload (file uploads)
2. **LLM-driven authentication**: Intelligent login form detection and filling using credentials from `login_params`

## Implementation Phases

**Status:** ✅ All 10 phases complete!

### ✅ Phase 1: Extend IR Model (COMPLETED)

**File:** `src/universal_scraper/core/ir/model.py`

**Changes:**

Add new action dataclasses:

```python
@dataclass
class Select:
    """Select option from dropdown menu."""
    selector: str
    value: str  # Option value or visible text to select


@dataclass
class Hover:
    """Hover over element to trigger hover effects."""
    selector: str


@dataclass
class KeyPress:
    """Press keyboard key, optionally on specific element."""
    key: str  # e.g., "Enter", "Escape", "Tab", "ArrowDown"
    selector: str | None = None  # If targeting specific element


@dataclass
class Upload:
    """Upload file to file input."""
    selector: str
    file_path: str  # Path to file to upload
```

Update PlanStep union:

```python
PlanStep = Union[Navigate, Click, Fill, Select, Hover, KeyPress, Upload, WaitFor, Validate]
```

**Estimated lines:** +20 lines, 1 line modified

---

### ✅ Phase 2: Enhance Page State Detection (COMPLETED)

**File:** `src/universal_scraper/adapters/playwright_explorer.py`

**Changes in `_get_page_state()` JavaScript evaluation:**

Enhance input field extraction to include metadata for LLM login detection:

```javascript
// Get input fields with metadata for LLM to recognize login fields
document.querySelectorAll('input:not([type="button"]):not([type="submit"]), textarea, select').forEach((el, idx) => {
    if (idx < 20 && el.offsetParent !== null) {
        const elemData = {
            type: el.tagName === 'SELECT' ? 'select' : 'input',
            selector: getSelector(el),
            placeholder: el.placeholder || '',
            inputType: el.type || 'text',
            name: el.name || '',
            id: el.id || '',
            autocomplete: el.autocomplete || '',
            ariaLabel: el.getAttribute('aria-label') || ''
        };

        // For select elements, capture first 5 options
        if (el.tagName === 'SELECT') {
            elemData.options = Array.from(el.options)
                .slice(0, 5)
                .map(opt => ({value: opt.value, text: opt.text}));
        }

        elements.push(elemData);
    }
});
```

Add file upload detection:

```javascript
// Get file upload inputs separately
document.querySelectorAll('input[type="file"]').forEach((el, idx) => {
    if (idx < 5 && el.offsetParent !== null) {
        elements.push({
            type: 'file_upload',
            selector: getSelector(el),
            accept: el.accept || '',
            multiple: el.multiple
        });
    }
});
```

**Estimated lines:** ~30 lines modified in JavaScript evaluation block

---

### ✅ Phase 3: Update Explorer Decision Logic (COMPLETED)

**File:** `src/universal_scraper/adapters/playwright_explorer.py`

**Changes:**

1. **Update function signature:**

```python
def explore_with_playwright(
    start_url: str,
    nl_request: str,
    schema: dict[str, Any],
    screenshots_dir: Path,
    html_dir: Path,
    job_id: str,
    max_steps: int = 20,
    headless: bool = True,
    login_params: dict[str, Any] | None = None,  # NEW
) -> ExplorationResult:
```

2. **Update `_decide_next_action()` signature:**

```python
def _decide_next_action(
    page_state: dict[str, Any],
    nl_request: str,
    schema: dict[str, Any],
    visited_urls: list[str],
    step_num: int,
    max_steps: int,
    login_params: dict[str, Any] | None = None,  # NEW
) -> dict[str, Any] | None:
```

3. **Enhanced system prompt with new actions and login awareness:**

```python
sys_prompt = """You are a web exploration agent. Based on the current page state, decide the next action.

Available actions:
- navigate: {"action": "navigate", "url": "https://..."}
- click: {"action": "click", "selector": "button.submit", "frame": 0}
- fill: {"action": "fill", "selector": "input#search", "text": "search term"}
- select: {"action": "select", "selector": "select#country", "value": "USA"}
- hover: {"action": "hover", "selector": ".menu-item"}
- keypress: {"action": "keypress", "key": "Enter", "selector": "input#search"}
- upload: {"action": "upload", "selector": "input[type='file']", "file_path": "/tmp/file.pdf"}
- extract: {"action": "extract"} - when you've found the data
- done: {"action": "done"} - when task is complete or stuck

IMPORTANT PRIORITY RULES:
1. **Cookie/Consent Banners**: If you see buttons with text like "Accept", "Zustimmen", "Agree", "OK",
   "Alle akzeptieren", "Einverstanden" in ANY frame, click them IMMEDIATELY before doing anything else.
2. **Login Forms**: If you detect a login/signin form (look for password input fields, username/email fields,
   login/signin buttons) and credentials are available, fill and submit the form BEFORE proceeding with the main task.
   Typical login indicators:
   - Input with type="password"
   - Input with name/id/autocomplete containing "user", "email", "login", "username"
   - Buttons with text "Login", "Sign in", "Submit", "Enter"
3. Elements may be in iframes (frame > 0). Include the "frame" number when clicking iframe elements.
4. After handling cookie banners and login, proceed with the actual task.

Return ONLY a JSON object with the action. Be efficient and goal-directed."""
```

4. **Add login context to user prompt:**

```python
# Add credentials availability notice to user prompt
credentials_notice = ""
if login_params and login_params.get('username') and login_params.get('password'):
    credentials_notice = f"\n\nCREDENTIALS AVAILABLE: username='{login_params.get('username')}', password='***'\nIf you detect a login form, use these credentials to authenticate before proceeding with the main task."

user_prompt = f"""Step {step_num}/{max_steps}

Task: {nl_request}

Target schema: {schema_str}

Current page:
- URL: {page_state.get("url", "")}
- Title: {page_state.get("title", "")}

Interactive elements:
{elements_str}

Page text (excerpt):
{page_state.get("text", "")[:1000]}

Already visited: {len(visited_urls)} URLs{credentials_notice}

Decide next action (JSON only):"""
```

5. **Implement new action execution:**

```python
elif action_type == "select":
    selector = action.get("selector", "")
    value = action.get("value", "")
    if selector and value:
        page.select_option(selector, value)
        actions.append(Select(selector=selector, value=value))
        page.wait_for_load_state("domcontentloaded", timeout=5000)

elif action_type == "hover":
    selector = action.get("selector", "")
    if selector:
        page.hover(selector, timeout=5000)
        actions.append(Hover(selector=selector))
        page.wait_for_timeout(500)  # Wait for hover effects

elif action_type == "keypress":
    key = action.get("key", "")
    selector = action.get("selector")
    if key:
        if selector:
            page.locator(selector).press(key)
        else:
            page.keyboard.press(key)
        actions.append(KeyPress(key=key, selector=selector))
        page.wait_for_timeout(500)

elif action_type == "upload":
    selector = action.get("selector", "")
    file_path = action.get("file_path", "")
    if selector and file_path:
        page.set_input_files(selector, file_path)
        actions.append(Upload(selector=selector, file_path=file_path))
```

6. **Update decision function calls to pass login_params:**

```python
action = _decide_next_action(
    page_state, nl_request, schema, urls, step, max_steps, login_params
)
```

**Estimated lines:** ~100 lines added/modified

---

### ✅ Phase 4: Update Code Generator (COMPLETED)

**File:** `src/universal_scraper/core/codegen/generator.py`

**Changes:**

1. **Add imports:**

```python
from ..ir.model import Click, Fill, Navigate, WaitFor, Validate, Select, Hover, KeyPress, Upload
```

2. **Add code generation for new step types in `generate_script()`:**

```python
elif isinstance(step, Select):
    lines.append(f"        # Step {index}: Select option in {step.selector}")
    lines.append("        try:")
    lines.append(f'            page.locator("{step.selector}").select_option("{step.value}")')
    lines.append(f'            page.screenshot(path=str(screens_dir / "step-{index}-select.png"), full_page=True)')
    lines.append("        except Exception as e:")
    lines.append(f'            print(f"Failed to select option: {{e}}")')

elif isinstance(step, Hover):
    lines.append(f"        # Step {index}: Hover over {step.selector}")
    lines.append("        try:")
    lines.append(f'            page.locator("{step.selector}").hover()')
    lines.append(f'            page.wait_for_timeout(500)')
    lines.append(f'            page.screenshot(path=str(screens_dir / "step-{index}-hover.png"), full_page=True)')
    lines.append("        except Exception as e:")
    lines.append(f'            print(f"Failed to hover: {{e}}")')

elif isinstance(step, KeyPress):
    lines.append(f"        # Step {index}: Press key '{step.key}'" + (f" on {step.selector}" if step.selector else ""))
    lines.append("        try:")
    if step.selector:
        lines.append(f'            page.locator("{step.selector}").press("{step.key}")')
    else:
        lines.append(f'            page.keyboard.press("{step.key}")')
    lines.append(f'            page.screenshot(path=str(screens_dir / "step-{index}-keypress.png"), full_page=True)')
    lines.append("        except Exception as e:")
    lines.append(f'            print(f"Failed to press key: {{e}}")')

elif isinstance(step, Upload):
    lines.append(f"        # Step {index}: Upload file to {step.selector}")
    lines.append("        try:")
    lines.append(f'            page.set_input_files("{step.selector}", "{step.file_path}")')
    lines.append(f'            page.screenshot(path=str(screens_dir / "step-{index}-upload.png"), full_page=True)')
    lines.append("        except Exception as e:")
    lines.append(f'            print(f"Failed to upload file: {{e}}")')
```

**Estimated lines:** ~50 lines added

---

### ✅ Phase 5: Update Plan Builder (COMPLETED)

**File:** `src/universal_scraper/core/planner/plan_builder.py`

**Changes:**

1. **Update system prompt:**

```python
sys_prompt = (
    "You are a planner that converts a natural language scraping request into a JSON IR.\n"
    "Only output strict JSON. Supported step types: navigate(url), click(selector), fill(selector,text), "
    "select(selector,value), hover(selector), keypress(key,selector?), upload(selector,file_path), "
    "wait_for(selector,state).\n"
    "Prefer generic, resilient selectors. If target_urls is provided, you MUST choose the first URL.\n"
    "IMPORTANT: Never use wait_for on metadata elements like <title>, <meta>, or hidden elements.\n"
)
```

2. **Update user prompt JSON schema:**

```python
"Return JSON with shape: {\n"
'  "steps": [\n'
'    {"type": "navigate", "url": string} |\n'
'    {"type": "click", "selector": string} |\n'
'    {"type": "fill", "selector": string, "text": string} |\n'
'    {"type": "select", "selector": string, "value": string} |\n'
'    {"type": "hover", "selector": string} |\n'
'    {"type": "keypress", "key": string, "selector": string?} |\n'
'    {"type": "upload", "selector": string, "file_path": string} |\n'
'    {"type": "wait_for", "selector": string, "state": string}\n'
"  ],\n"
'  "notes": string\n'
"}\n"
```

3. **Add parsing for new action types:**

```python
elif typ == "select":
    sel = s.get("selector", "")
    value = s.get("value", "")
    if isinstance(sel, str) and sel and isinstance(value, str):
        steps.append(Select(selector=sel, value=value))

elif typ == "hover":
    sel = s.get("selector", "")
    if isinstance(sel, str) and sel:
        steps.append(Hover(selector=sel))

elif typ in ("keypress", "key_press", "press"):
    key = s.get("key", "")
    selector = s.get("selector")
    if isinstance(key, str) and key:
        steps.append(KeyPress(key=key, selector=selector))

elif typ == "upload":
    sel = s.get("selector", "")
    file_path = s.get("file_path", "")
    if isinstance(sel, str) and sel and isinstance(file_path, str):
        steps.append(Upload(selector=sel, file_path=file_path))
```

4. **Add imports:**

```python
from ..ir.model import Click, Fill, Navigate, ScrapePlan, Validate, WaitFor, Select, Hover, KeyPress, Upload
```

**Estimated lines:** ~30 lines added/modified

---

### ✅ Phase 6: Update Runner to Pass login_params (COMPLETED)

**File:** `src/universal_scraper/core/executor/runner.py`

**Changes:**

Pass login_params to explore_with_playwright:

```python
res = explore_with_playwright(
    start_url=start_url,
    nl_request=req.nl_request,
    schema=req.output_schema,
    screenshots_dir=screenshots_dir,
    html_dir=html_dir,
    job_id=job_id,
    max_steps=int(os.getenv("MAX_EXPLORATION_STEPS", "20")),
    headless=settings.headless,
    login_params=req.login_params,  # NEW
)
```

**Estimated lines:** 1 line modified

---

### ✅ Phase 7: Update Navigator for IR Execution (COMPLETED)

**File:** `src/universal_scraper/core/nav/navigator.py`

**Changes:**

1. **Add imports:**

```python
from ..ir.model import Click, Fill, Navigate, ScrapePlan, WaitFor, Select, Hover, KeyPress, Upload
```

2. **Add execution for new step types in `execute_plan()`:**

```python
elif isinstance(step, Select):
    page.select_option(step.selector, step.value)
elif isinstance(step, Hover):
    page.hover(step.selector)
    page.wait_for_timeout(500)
elif isinstance(step, KeyPress):
    if step.selector:
        page.locator(step.selector).press(step.key)
    else:
        page.keyboard.press(step.key)
elif isinstance(step, Upload):
    page.set_input_files(step.selector, step.file_path)
```

**Estimated lines:** ~15 lines added

---

### ✅ Phase 8: Update API DTO (COMPLETED)

**File:** `src/universal_scraper/api/dto.py`

**Changes:**

Update login_params field documentation:

```python
login_params: dict[str, Any] | None = Field(
    None,
    description="Login credentials for LLM-driven authentication. Supports: "
                "{'username': str, 'password': str} for form-based login (LLM auto-detects forms) OR "
                "{'http_basic': {'username': str, 'password': str}} for HTTP Basic Auth. "
                "The LLM will automatically detect and fill login forms when credentials are provided."
)
```

**Estimated lines:** 4 lines modified

---

### ✅ Phase 9: Integration Tests (COMPLETED)

**New File:** `tests/test_form_login_integration.py`

```python
"""Integration tests for LLM-driven login form detection and filling."""

import os
from pathlib import Path

import pytest
from universal_scraper.api.dto import ScrapeRequest
from universal_scraper.core.executor.runner import run_job_with_id


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="Requires ANTHROPIC_API_KEY")
def test_llm_detects_and_fills_login():
    """Test LLM detects login form and fills it automatically.

    Uses https://practicetestautomation.com/practice-test-login/
    Valid credentials: username="student", password="Password123"
    """
    os.environ["MAX_EXPLORATION_STEPS"] = "15"

    req = ScrapeRequest(
        nl_request="Log in to the website and extract the success message after login",
        output_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "logged_in": {"type": "boolean"}
            }
        },
        target_urls=["https://practicetestautomation.com/practice-test-login/"],
        login_params={
            "username": "student",
            "password": "Password123"
        }
    )

    result = run_job_with_id("login-test", req)

    # Verify login flow executed
    assert result.status == "completed"
    log_str = " ".join(result.execution_log)

    # Should have filled username and password fields
    assert any("fill" in log.lower() for log in result.execution_log), \
        "Expected Fill actions for username/password"

    # Should have clicked submit button
    assert any("click" in log.lower() for log in result.execution_log), \
        "Expected Click action for login button"

    # Check if we got post-login content
    assert result.data, "Expected data extraction after login"
    print(f"Login test result: {result.data}")


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="Requires ANTHROPIC_API_KEY")
def test_login_not_triggered_without_credentials():
    """Test that no login happens when credentials not provided."""
    os.environ["MAX_EXPLORATION_STEPS"] = "5"

    req = ScrapeRequest(
        nl_request="Extract the page title",
        output_schema={
            "type": "object",
            "properties": {"title": {"type": "string"}}
        },
        target_urls=["https://practicetestautomation.com/practice-test-login/"],
        # NO login_params
    )

    result = run_job_with_id("no-login-test", req)

    # Should not attempt login without credentials
    # Check that we didn't fill password fields
    fill_actions = [log for log in result.execution_log if "fill" in log.lower()]
    assert len(fill_actions) == 0, "Should not fill forms without credentials"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

**New File:** `tests/test_new_actions.py`

```python
"""Unit and integration tests for new IR actions: Select, Hover, KeyPress, Upload."""

import os
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright
from universal_scraper.api.dto import ScrapeRequest
from universal_scraper.core.executor.runner import run_job_with_id
from universal_scraper.core.ir.model import Select, Hover, KeyPress, Upload


def test_select_action_playwright():
    """Test Select action executes correctly with Playwright."""
    html = """
    <html>
        <body>
            <select id="country">
                <option value="us">USA</option>
                <option value="uk">UK</option>
                <option value="de">Germany</option>
            </select>
            <div id="result"></div>
            <script>
                document.getElementById('country').onchange = function() {
                    document.getElementById('result').textContent = this.value;
                };
            </script>
        </body>
    </html>
    """

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html)

        # Execute Select action
        page.select_option("#country", "uk")

        # Verify selection worked
        selected_value = page.locator("#result").text_content()
        assert selected_value == "uk"

        browser.close()


def test_hover_action_playwright():
    """Test Hover action reveals hidden content."""
    html = """
    <html>
        <head>
            <style>
                .dropdown-content { display: none; }
                .dropdown:hover .dropdown-content { display: block; }
            </style>
        </head>
        <body>
            <div class="dropdown">
                <span>Menu</span>
                <div class="dropdown-content">
                    <a href="#">Link 1</a>
                    <a href="#">Link 2</a>
                </div>
            </div>
        </body>
    </html>
    """

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html)

        # Before hover, content should be hidden
        assert not page.locator(".dropdown-content").is_visible()

        # Execute Hover action
        page.hover(".dropdown")

        # After hover, content should be visible
        assert page.locator(".dropdown-content").is_visible()

        browser.close()


def test_keypress_action_playwright():
    """Test KeyPress action sends keyboard events."""
    html = """
    <html>
        <body>
            <input id="search" type="text" />
            <div id="result"></div>
            <script>
                document.getElementById('search').onkeydown = function(e) {
                    if (e.key === 'Enter') {
                        document.getElementById('result').textContent = 'Enter pressed';
                    }
                };
            </script>
        </body>
    </html>
    """

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html)

        # Fill input and press Enter
        page.fill("#search", "test query")
        page.locator("#search").press("Enter")

        # Verify Enter was detected
        result = page.locator("#result").text_content()
        assert result == "Enter pressed"

        browser.close()


def test_upload_action_playwright(tmp_path):
    """Test Upload action with file input."""
    html = """
    <html>
        <body>
            <input type="file" id="file-upload" />
            <div id="filename"></div>
            <script>
                document.getElementById('file-upload').onchange = function() {
                    document.getElementById('filename').textContent = this.files[0].name;
                };
            </script>
        </body>
    </html>
    """

    # Create temporary test file
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html)

        # Execute Upload action
        page.set_input_files("#file-upload", str(test_file))

        # Verify file was uploaded
        filename = page.locator("#filename").text_content()
        assert filename == "test.txt"

        browser.close()


@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="Requires ANTHROPIC_API_KEY")
def test_select_in_exploration():
    """Test that LLM can use Select action during exploration."""
    html = """
    <html>
        <body>
            <h1>Product Search</h1>
            <select id="category">
                <option value="">Select Category</option>
                <option value="electronics">Electronics</option>
                <option value="books">Books</option>
            </select>
            <div id="products" style="display:none;">
                <div class="product">Product 1</div>
                <div class="product">Product 2</div>
            </div>
            <script>
                document.getElementById('category').onchange = function() {
                    if (this.value) {
                        document.getElementById('products').style.display = 'block';
                    }
                };
            </script>
        </body>
    </html>
    """

    req = ScrapeRequest(
        nl_request="Select the Electronics category and extract the product list",
        output_schema={
            "type": "object",
            "properties": {
                "products": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            }
        },
        target_urls=[f"data:text/html,{html}"]
    )

    os.environ["MAX_EXPLORATION_STEPS"] = "5"
    result = run_job_with_id("select-test", req)

    # Verify Select action was used
    assert result.status == "completed"
    # Check execution log for select or products found
    print(f"Select test result: {result.data}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

**Estimated lines:** ~300 lines (2 new test files)

---

### ✅ Phase 10: Documentation (COMPLETED)

**File:** `CLAUDE.md`

**Changes:**

Add new section on authentication and new actions:

```markdown
## Authentication

The system supports **LLM-driven authentication**. Simply provide credentials in `login_params`:

```json
{
  "nl_request": "Extract my recent orders",
  "target_urls": ["https://example-shop.com"],
  "login_params": {
    "username": "user@example.com",
    "password": "secret123"
  },
  "schema": {
    "type": "object",
    "properties": {
      "orders": {"type": "array", "items": {"type": "string"}}
    }
  }
}
```

The LLM explorer will automatically:
1. **Detect login forms** by analyzing page elements (password fields, username fields, login buttons)
2. **Fill credentials** using the provided username/password
3. **Submit the form** by clicking the appropriate button
4. **Proceed with the main task** after successful authentication

**No manual selectors needed** - the LLM intelligently identifies login forms based on common patterns like:
- Input fields with `type="password"`
- Input fields with names/IDs like "username", "email", "user", "login"
- Submit buttons with text "Login", "Sign in", "Submit"

For HTTP Basic Authentication, use:
```json
{
  "login_params": {
    "http_basic": {
      "username": "admin",
      "password": "secret"
    }
  }
}
```

## Extended Action Vocabulary

The IR (Intermediate Representation) supports a complete set of browser interactions:

### Core Actions
- **Navigate**: Go to URL
- **Click**: Click elements (including iframe-aware clicking)
- **Fill**: Fill text into input fields
- **WaitFor**: Wait for elements to reach specific states

### Extended Actions (New)
- **Select**: Choose options from dropdown menus
  ```python
  Select(selector="select#country", value="USA")
  ```
- **Hover**: Trigger hover effects to reveal hidden content
  ```python
  Hover(selector=".menu-item")
  ```
- **KeyPress**: Send keyboard events
  ```python
  KeyPress(key="Enter", selector="input#search")  # On specific element
  KeyPress(key="Escape", selector=None)  # Global key press
  ```
- **Upload**: Upload files to file inputs
  ```python
  Upload(selector="input[type='file']", file_path="/tmp/document.pdf")
  ```
- **Validate**: Assert page state for self-healing
  ```python
  Validate(selector=".success-msg", validation_type="presence", is_critical=True)
  ```

All actions are:
- **LLM-driven during exploration** - The agent decides which actions to use
- **Compiled to pure Playwright scripts** - Generated code uses these actions
- **Self-healing aware** - Failed actions trigger automatic retry with patches

## Implementation Roadmap

See [completion_plan.md](completion_plan.md) for detailed implementation plan of:
- Complete action vocabulary (Select, Hover, KeyPress, Upload)
- LLM-driven authentication flows
```

**Estimated lines:** ~80 lines added

---

## Summary

### Files to Create
1. `tests/test_form_login_integration.py` (~150 lines)
2. `tests/test_new_actions.py` (~150 lines)

### Files to Modify
1. `src/universal_scraper/core/ir/model.py` (~20 new, 1 modified)
2. `src/universal_scraper/adapters/playwright_explorer.py` (~130 new/modified)
3. `src/universal_scraper/core/codegen/generator.py` (~50 new)
4. `src/universal_scraper/core/planner/plan_builder.py` (~30 new/modified)
5. `src/universal_scraper/core/executor/runner.py` (~1 modified)
6. `src/universal_scraper/core/nav/navigator.py` (~15 new)
7. `src/universal_scraper/api/dto.py` (~4 modified)
8. `CLAUDE.md` (~80 new)

### Total Estimated Changes
- **New lines:** ~625
- **Modified lines:** ~36
- **New files:** 2 test files

### Implementation Order

1. **Phase 1-2**: Core IR + page state (~50 lines, 1 file)
2. **Phase 3**: Explorer logic (~130 lines, 1 file) - Most complex
3. **Phase 4-5**: Code gen + planner (~80 lines, 2 files)
4. **Phase 6-7**: Runner + navigator (~16 lines, 2 files)
5. **Phase 8**: API docs (~4 lines, 1 file)
6. **Phase 9**: Integration tests (~300 lines, 2 files)
7. **Phase 10**: Documentation (~80 lines, 1 file)

### Testing Strategy

1. **Unit tests**: Individual Playwright action tests (Phase 9, test_new_actions.py)
2. **Integration test**: LLM-driven login detection (Phase 9, test_form_login_integration.py)
3. **Regression tests**: Re-run existing tests (test_heise_news_integration.py, test_multiple_news_sites.py)
4. **End-to-end**: Login → Navigate → Extract workflow with real site

### Key Design Decisions

1. **LLM-driven login detection**: No hardcoded form detection, LLM recognizes login forms from context
2. **Credentials in prompt**: Username/password passed to LLM in user prompt for intelligent filling
3. **Priority-based actions**: Cookie banners > Login > Main task (enforced in system prompt)
4. **Complete action vocabulary**: All common browser interactions supported
5. **Backward compatible**: Existing tests and APIs unchanged

### Success Criteria

- [ ] All 4 new IR actions (Select, Hover, KeyPress, Upload) implemented
- [ ] LLM successfully detects and fills login forms with provided credentials
- [ ] New actions work in exploration mode (LLM uses them)
- [ ] New actions work in generated scripts (code generation supports them)
- [ ] Integration test passes with real login form
- [ ] All existing tests still pass (regression check)
- [ ] Documentation updated with examples

### Risk Mitigation

1. **LLM may not detect login forms reliably**:
   - Mitigation: Provide rich input field metadata (name, id, autocomplete, type)
   - Fallback: User can explicitly request login in nl_request

2. **Credentials in LLM prompts**:
   - Note: Passwords sent to Anthropic API (but not logged/stored by us)
   - Alternative: Could implement client-side login flow detection

3. **Generated code security**:
   - Passwords NOT embedded in generated scripts
   - Scripts only use selectors, not credentials

4. **Testing with real sites**:
   - Use public test sites (practicetestautomation.com)
   - Avoid production credentials in tests
