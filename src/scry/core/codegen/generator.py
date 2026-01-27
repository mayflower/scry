"""Playwright Python code generation (V3).

Generates a self-contained Python script that:
- Launches Chromium (headless toggle via injected const)
- Executes step types: Navigate, Click, Fill, WaitFor, Validate, Select, Hover, KeyPress, Upload
- Captures screenshots and HTML snapshots at each step
- Performs data extraction based on the extraction spec

No AI at runtime; purely deterministic.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..ir.model import (
    Click,
    Fill,
    Hover,
    KeyPress,
    Navigate,
    ScrapePlan,
    Select,
    Upload,
    Validate,
    WaitFor,
)

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

# Code generation constants to avoid duplication
_INDENT = "        "
_TRY_BLOCK = f"{_INDENT}try:"
_NESTED_INDENT = f"{_INDENT}    "
_EXCEPT_BLOCK = f"{_INDENT}except Exception as e:"
# Extraction block indentation (16 spaces = 4 levels)
_EXTRACT_INDENT = "                "
_EXTRACT_TRY = f"{_EXTRACT_INDENT}try:"


def _wrap_in_try_except(
    action_lines: list[str], error_msg: str, indent: str = _INDENT
) -> list[str]:
    """Wrap action lines in try/except with a print statement for the error."""
    nested = indent + "    "
    lines = [f"{indent}try:"]
    for line in action_lines:
        lines.append(f"{nested}{line}")
    lines.append(f"{indent}except Exception as e:")
    lines.append(f'{nested}print(f"{error_msg}: {{e}}")')
    return lines


TEMPLATE = """#!/usr/bin/env python3
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ARTIFACTS_ROOT = Path(r"{artifacts_root}")
JOB_ID = "{job_id}"
HEADLESS = {headless}
TIMEOUT_MS = 30000
EXTRA_WAIT_MS = {extra_wait_ms}
WAIT_LOAD_STATE = {wait_load_state}
EXTRACTION_SPEC = json.loads('{extraction_spec}')

screens_dir = ARTIFACTS_ROOT / "screenshots" / JOB_ID
html_dir = ARTIFACTS_ROOT / "html"
data_dir = ARTIFACTS_ROOT / "data"
screens_dir.mkdir(parents=True, exist_ok=True)
html_dir.mkdir(parents=True, exist_ok=True)
data_dir.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=HEADLESS)
    try:
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(TIMEOUT_MS)
        if WAIT_LOAD_STATE:
            try:
                page.wait_for_load_state("networkidle")
            except Exception:
                pass
{steps}
    finally:
        browser.close()
"""


# --- Step Renderers ---


def _render_navigate(
    step: Navigate,
    index: int,
    page_num: int,
    cookie_dismiss_selector: str | None,
) -> list[str]:
    """Render a Navigate step."""
    lines: list[str] = []
    safe_url = (
        step.url.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r").replace('"', '\\"')
    )
    comment_url = step.url[:50].replace("\n", " ").replace("\r", " ")
    lines.append(f"        # Step {index}: Navigate to {comment_url}...")
    lines.append(f'        page.goto("{safe_url}")')

    if page_num == 1 and cookie_dismiss_selector:
        escaped_selector = cookie_dismiss_selector.replace('"', '\\"')
        lines.append(
            f'        try:\n            page.locator("{escaped_selector}").click(timeout=2000)\n        except Exception:\n            pass'
        )

    lines.append(
        f'        page.screenshot(path=str(screens_dir / "step-{index}.png"), full_page=True)'
    )
    lines.append(f'        html_out = html_dir / f"{{JOB_ID}}-page-{page_num}.html"')
    lines.append('        html_out.write_text(page.content(), encoding="utf-8")')
    lines.append('        page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")')
    lines.append(
        f'        page.screenshot(path=str(screens_dir / "step-{index}-scroll.png"), full_page=True)'
    )
    return lines


def _render_click(step: Click, index: int) -> list[str]:
    """Render a Click step."""
    lines = [f"        # Step {index}: Click {step.selector}"]
    lines.extend(
        _wrap_in_try_except(
            [
                f'page.locator("{step.selector}").click(timeout=5000)',
                'page.wait_for_load_state("domcontentloaded", timeout=5000)',
                f'page.screenshot(path=str(screens_dir / "step-{index}-click.png"), full_page=True)',
            ],
            f"Failed to click {step.selector}",
        )
    )
    return lines


def _render_fill(step: Fill, index: int) -> list[str]:
    """Render a Fill step."""
    lines = [f"        # Step {index}: Fill {step.selector} with text"]
    lines.extend(
        _wrap_in_try_except(
            [
                f'page.locator("{step.selector}").fill("{step.text}")',
                f'page.screenshot(path=str(screens_dir / "step-{index}-fill.png"), full_page=True)',
            ],
            f"Failed to fill {step.selector}",
        )
    )
    return lines


def _render_wait_for(step: WaitFor, index: int) -> list[str]:
    """Render a WaitFor step."""
    state_map = {
        "visible": "visible",
        "hidden": "hidden",
        "attached": "attached",
        "detached": "detached",
    }
    state = state_map.get(step.state, "visible")
    lines = [f"        # Step {index}: Wait for {step.selector}"]
    lines.extend(
        _wrap_in_try_except(
            [f'page.locator("{step.selector}").first.wait_for(state="{state}", timeout=10000)'],
            "Timeout waiting for selector",
        )
    )
    return lines


def _render_validate_body(step: Validate) -> list[str]:
    """Render the validation logic based on type."""
    lines: list[str] = []
    if step.validation_type == "presence":
        lines.append("            if not element.is_visible(timeout=5000):")
        lines.append(
            f'                raise Exception("Validation failed: element not found - {step.description}")'
        )
    elif step.validation_type == "absence":
        lines.append("            if element.is_visible(timeout=1000):")
        lines.append(
            f'                raise Exception("Validation failed: element should not be present - {step.description}")'
        )
    elif step.validation_type == "text" and step.expected_text:
        lines.append("            actual_text = element.text_content()")
        lines.append(f'            if "{step.expected_text}" not in actual_text:')
        lines.append(
            f'                raise Exception("Validation failed: text mismatch - {step.description}")'
        )
    elif step.validation_type == "count" and step.expected_count:
        lines.append(f"            if element.count() != {step.expected_count}:")
        lines.append(
            f'                raise Exception("Validation failed: count mismatch - {step.description}")'
        )
    return lines


def _render_validate(step: Validate, index: int) -> list[str]:
    """Render a Validate step."""
    lines = [
        f"        # Step {index}: Validate {step.description or step.selector}",
        "        try:",
        f'            element = page.locator("{step.selector}")',
    ]
    lines.extend(_render_validate_body(step))
    lines.append(f'            print("Validation passed: {step.description}")')
    lines.append("        except Exception as e:")

    if step.is_critical:
        lines.append('            print(f"CRITICAL validation failed: {e}")')
        lines.append("            import sys")
        lines.append("            sys.exit(1)  # Exit for self-healing")
    else:
        lines.append('            print(f"Non-critical validation failed: {e}")')
    return lines


def _render_select(step: Select, index: int) -> list[str]:
    """Render a Select step."""
    lines = [f"        # Step {index}: Select option in {step.selector}"]
    lines.extend(
        _wrap_in_try_except(
            [
                f'page.locator("{step.selector}").select_option("{step.value}")',
                f'page.screenshot(path=str(screens_dir / "step-{index}-select.png"), full_page=True)',
            ],
            "Failed to select option",
        )
    )
    return lines


def _render_hover(step: Hover, index: int) -> list[str]:
    """Render a Hover step."""
    lines = [f"        # Step {index}: Hover over {step.selector}"]
    lines.extend(
        _wrap_in_try_except(
            [
                f'page.locator("{step.selector}").hover()',
                "page.wait_for_timeout(500)",
                f'page.screenshot(path=str(screens_dir / "step-{index}-hover.png"), full_page=True)',
            ],
            "Failed to hover",
        )
    )
    return lines


def _render_keypress(step: KeyPress, index: int) -> list[str]:
    """Render a KeyPress step."""
    selector_text = f" on {step.selector}" if step.selector else ""
    key_action = (
        f'page.locator("{step.selector}").press("{step.key}")'
        if step.selector
        else f'page.keyboard.press("{step.key}")'
    )
    lines = [f"        # Step {index}: Press key '{step.key}'{selector_text}"]
    lines.extend(
        _wrap_in_try_except(
            [
                key_action,
                f'page.screenshot(path=str(screens_dir / "step-{index}-keypress.png"), full_page=True)',
            ],
            "Failed to press key",
        )
    )
    return lines


def _render_upload(step: Upload, index: int) -> list[str]:
    """Render an Upload step."""
    lines = [f"        # Step {index}: Upload file to {step.selector}"]
    lines.extend(
        _wrap_in_try_except(
            [
                f'page.set_input_files("{step.selector}", "{step.file_path}")',
                f'page.screenshot(path=str(screens_dir / "step-{index}-upload.png"), full_page=True)',
            ],
            "Failed to upload file",
        )
    )
    return lines


def _render_extraction_block() -> list[str]:
    """Render the extraction block that handles both simple and array extraction."""
    return [
        "        # Extraction per spec",
        "        result = {}",
        "        for field, spec in EXTRACTION_SPEC.items():",
        "            if isinstance(spec, dict) and 'fields' in spec:",
        "                # Array extraction with nested fields",
        "                parent_sel = spec.get('selector')",
        "                fields_spec = spec.get('fields', {})",
        "                limit = spec.get('limit', 10)",
        "                items = []",
        _EXTRACT_TRY,
        "                    elements = page.locator(parent_sel).all()[:limit]",
        "                    for elem in elements:",
        "                        item = {}",
        "                        for sub_field, sub_spec in fields_spec.items():",
        "                            sub_sel = sub_spec.get('selector', '')",
        "                            attr = sub_spec.get('attribute')",
        "                            try:",
        "                                sub_elem = elem.locator(sub_sel).first",
        "                                if attr:",
        "                                    value = sub_elem.get_attribute(attr)",
        "                                else:",
        "                                    value = sub_elem.text_content()",
        "                                if value:",
        "                                    item[sub_field] = value.strip()",
        "                            except Exception:",
        "                                pass",
        "                        if item:",
        "                            items.append(item)",
        "                    result[field] = items",
        "                except Exception as e:",
        "                    print(f'Array extraction failed for {field}: {e}')",
        "                    result[field] = []",
        "            else:",
        "                # Simple field extraction",
        "                sel = spec.get('selector') if isinstance(spec, dict) else None",
        "                if not sel: continue",
        _EXTRACT_TRY,
        "                    text = page.locator(sel).first.text_content()",
        "                    if text:",
        "                        text = text.strip()",
        "                    else:",
        "                        text = ''",
        "                except Exception:",
        "                    text = ''",
        "                rx = spec.get('regex') if isinstance(spec, dict) else None",
        "                if rx:",
        "                    import re",
        "                    m = re.search(rx, text)",
        "                    if m:",
        "                        text = m.group(1) if m.groups() else m.group(0)",
        "                # Attempt number cast",
        _EXTRACT_TRY,
        "                    if text and all(c.isdigit() or c in ',. ' for c in text):",
        "                        num = int(''.join([c for c in text if c.isdigit()]))",
        "                        result[field] = num",
        "                    else:",
        "                        result[field] = text",
        "                except Exception:",
        "                    result[field] = text",
        "        (data_dir / f\"{JOB_ID}.json\").write_text(__import__('json').dumps(result), encoding='utf-8')",
    ]


def _render_steps(
    plan: ScrapePlan,
    cookie_dismiss_selector: str | None = None,
) -> str:
    """Render all steps in a plan to code."""
    lines: list[str] = []
    page_num = 0

    for index, step in enumerate(plan.steps, start=1):
        if isinstance(step, Navigate):
            page_num += 1
            lines.extend(_render_navigate(step, index, page_num, cookie_dismiss_selector))
        elif isinstance(step, Click):
            lines.extend(_render_click(step, index))
        elif isinstance(step, Fill):
            lines.extend(_render_fill(step, index))
        elif isinstance(step, WaitFor):
            lines.extend(_render_wait_for(step, index))
        elif isinstance(step, Validate):
            lines.extend(_render_validate(step, index))
        elif isinstance(step, Select):
            lines.extend(_render_select(step, index))
        elif isinstance(step, Hover):
            lines.extend(_render_hover(step, index))
        elif isinstance(step, KeyPress):
            lines.extend(_render_keypress(step, index))
        elif isinstance(step, Upload):
            lines.extend(_render_upload(step, index))

    lines.extend(_render_extraction_block())
    return "\n".join(lines)


def generate_script(
    plan: ScrapePlan,
    job_id: str,
    artifacts_root: Path,
    headless: bool,
    options: dict[str, Any] | None = None,
) -> Path:
    import json

    options = options or {}
    steps_code = _render_steps(
        plan,
        cookie_dismiss_selector=options.get("cookie_dismiss_selector"),
    )
    # Properly serialize the extraction_spec and escape backslashes for embedding in Python string
    extraction_spec = json.dumps(options.get("extraction_spec", {})).replace("\\", "\\\\")

    script = TEMPLATE.format(
        artifacts_root=str(artifacts_root),
        job_id=job_id,
        headless=str(bool(headless)),
        steps=steps_code,
        extra_wait_ms=int(options.get("extra_wait_ms", 0)),
        wait_load_state=str(bool(options.get("wait_load_state", False))),
        extraction_spec=extraction_spec,
    )
    out_dir = artifacts_root / "generated_code"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{job_id}.py"
    out_path.write_text(script, encoding="utf-8")
    try:
        out_path.chmod(0o755)
    except OSError as e:
        logger.debug("chmod failed on %s: %s", out_path, e)
    return out_path
