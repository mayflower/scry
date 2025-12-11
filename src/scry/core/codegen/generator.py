"""Playwright Python code generation (V3).

Generates a self-contained Python script that:
- Launches Chromium (headless toggle via injected const)
- Executes Navigate steps
- Captures screenshots and first page HTML

No AI at runtime; purely deterministic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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


def _render_steps(plan: ScrapePlan, handle_cookie_banner: bool) -> str:
    lines: list[str] = []
    index = 0
    page_num = 0

    for step in plan.steps:
        index += 1

        if isinstance(step, Navigate):
            page_num += 1
            # Escape newlines and quotes in URLs (especially for data: URLs)
            safe_url = (
                step.url.replace("\\", "\\\\")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace('"', '\\"')
            )
            # For comment, also clean the URL to avoid breaking across lines
            comment_url = step.url[:50].replace("\n", " ").replace("\r", " ")
            lines.append(f"        # Step {index}: Navigate to {comment_url}...")
            lines.append(f'        page.goto("{safe_url}")')
            if handle_cookie_banner and page_num == 1:  # Only on first navigation
                lines.append(
                    "        try:\n            page.get_by_role('button', name='Accept').click(timeout=1000)\n        except Exception:\n            pass"
                )
            lines.append(
                f'        page.screenshot(path=str(screens_dir / "step-{index}.png"), full_page=True)'
            )
            lines.append(
                f'        html_out = html_dir / f"{{JOB_ID}}-page-{page_num}.html"'
            )
            lines.append(
                '        html_out.write_text(page.content(), encoding="utf-8")'
            )
            lines.append(
                '        page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")'
            )
            lines.append(
                f'        page.screenshot(path=str(screens_dir / "step-{index}-scroll.png"), full_page=True)'
            )

        elif isinstance(step, Click):
            lines.append(f"        # Step {index}: Click {step.selector}")
            lines.append("        try:")
            lines.append(
                f'            page.locator("{step.selector}").click(timeout=5000)'
            )
            lines.append(
                '            page.wait_for_load_state("domcontentloaded", timeout=5000)'
            )
            lines.append(
                f'            page.screenshot(path=str(screens_dir / "step-{index}-click.png"), full_page=True)'
            )
            lines.append("        except Exception as e:")
            lines.append(
                f'            print(f"Failed to click {step.selector}: {{e}}")'
            )

        elif isinstance(step, Fill):
            lines.append(f"        # Step {index}: Fill {step.selector} with text")
            lines.append("        try:")
            lines.append(
                f'            page.locator("{step.selector}").fill("{step.text}")'
            )
            lines.append(
                f'            page.screenshot(path=str(screens_dir / "step-{index}-fill.png"), full_page=True)'
            )
            lines.append("        except Exception as e:")
            lines.append('            print(f"Failed to fill {step.selector}: {e}")')

        elif isinstance(step, WaitFor):
            lines.append(f"        # Step {index}: Wait for {step.selector}")
            lines.append("        try:")
            state_map = {
                "visible": "visible",
                "hidden": "hidden",
                "attached": "attached",
                "detached": "detached",
            }
            state = state_map.get(step.state, "visible")
            lines.append(
                f'            page.locator("{step.selector}").first.wait_for(state="{state}", timeout=10000)'
            )
            lines.append("        except Exception as e:")
            lines.append('            print(f"Timeout waiting for selector: {e}")')

        elif isinstance(step, Validate):
            lines.append(
                f"        # Step {index}: Validate {step.description or step.selector}"
            )
            lines.append("        try:")
            lines.append(f'            element = page.locator("{step.selector}")')

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
                lines.append(
                    f'            if "{step.expected_text}" not in actual_text:'
                )
                lines.append(
                    f'                raise Exception("Validation failed: text mismatch - {step.description}")'
                )
            elif step.validation_type == "count" and step.expected_count:
                lines.append(
                    f"            if element.count() != {step.expected_count}:"
                )
                lines.append(
                    f'                raise Exception("Validation failed: count mismatch - {step.description}")'
                )

            lines.append(f'            print("Validation passed: {step.description}")')
            lines.append("        except Exception as e:")
            if step.is_critical:
                lines.append('            print(f"CRITICAL validation failed: {e}")')
                lines.append("            import sys")
                lines.append("            sys.exit(1)  # Exit for self-healing")
            else:
                lines.append(
                    '            print(f"Non-critical validation failed: {e}")'
                )

        elif isinstance(step, Select):
            lines.append(f"        # Step {index}: Select option in {step.selector}")
            lines.append("        try:")
            lines.append(
                f'            page.locator("{step.selector}").select_option("{step.value}")'
            )
            lines.append(
                f'            page.screenshot(path=str(screens_dir / "step-{index}-select.png"), full_page=True)'
            )
            lines.append("        except Exception as e:")
            lines.append('            print(f"Failed to select option: {e}")')

        elif isinstance(step, Hover):
            lines.append(f"        # Step {index}: Hover over {step.selector}")
            lines.append("        try:")
            lines.append(f'            page.locator("{step.selector}").hover()')
            lines.append("            page.wait_for_timeout(500)")
            lines.append(
                f'            page.screenshot(path=str(screens_dir / "step-{index}-hover.png"), full_page=True)'
            )
            lines.append("        except Exception as e:")
            lines.append('            print(f"Failed to hover: {e}")')

        elif isinstance(step, KeyPress):
            selector_text = f" on {step.selector}" if step.selector else ""
            lines.append(
                f"        # Step {index}: Press key '{step.key}'{selector_text}"
            )
            lines.append("        try:")
            if step.selector:
                lines.append(
                    f'            page.locator("{step.selector}").press("{step.key}")'
                )
            else:
                lines.append(f'            page.keyboard.press("{step.key}")')
            lines.append(
                f'            page.screenshot(path=str(screens_dir / "step-{index}-keypress.png"), full_page=True)'
            )
            lines.append("        except Exception as e:")
            lines.append('            print(f"Failed to press key: {e}")')

        elif isinstance(step, Upload):
            lines.append(f"        # Step {index}: Upload file to {step.selector}")
            lines.append("        try:")
            lines.append(
                f'            page.set_input_files("{step.selector}", "{step.file_path}")'
            )
            lines.append(
                f'            page.screenshot(path=str(screens_dir / "step-{index}-upload.png"), full_page=True)'
            )
            lines.append("        except Exception as e:")
            lines.append('            print(f"Failed to upload file: {e}")')

    # Extraction block - handles both simple and array extraction
    lines.append("        # Extraction per spec")
    lines.append("        result = {}")
    lines.append("        for field, spec in EXTRACTION_SPEC.items():")
    lines.append("            if isinstance(spec, dict) and 'fields' in spec:")
    lines.append("                # Array extraction with nested fields")
    lines.append("                parent_sel = spec.get('selector')")
    lines.append("                fields_spec = spec.get('fields', {})")
    lines.append("                limit = spec.get('limit', 10)")
    lines.append("                items = []")
    lines.append("                try:")
    lines.append(
        "                    elements = page.locator(parent_sel).all()[:limit]"
    )
    lines.append("                    for elem in elements:")
    lines.append("                        item = {}")
    lines.append(
        "                        for sub_field, sub_spec in fields_spec.items():"
    )
    lines.append("                            sub_sel = sub_spec.get('selector', '')")
    lines.append("                            attr = sub_spec.get('attribute')")
    lines.append("                            try:")
    lines.append(
        "                                sub_elem = elem.locator(sub_sel).first"
    )
    lines.append("                                if attr:")
    lines.append(
        "                                    value = sub_elem.get_attribute(attr)"
    )
    lines.append("                                else:")
    lines.append("                                    value = sub_elem.text_content()")
    lines.append("                                if value:")
    lines.append("                                    item[sub_field] = value.strip()")
    lines.append("                            except Exception:")
    lines.append("                                pass")
    lines.append("                        if item:")
    lines.append("                            items.append(item)")
    lines.append("                    result[field] = items")
    lines.append("                except Exception as e:")
    lines.append(
        "                    print(f'Array extraction failed for {field}: {e}')"
    )
    lines.append("                    result[field] = []")
    lines.append("            else:")
    lines.append("                # Simple field extraction")
    lines.append(
        "                sel = spec.get('selector') if isinstance(spec, dict) else None"
    )
    lines.append("                if not sel: continue")
    lines.append("                try:")
    lines.append("                    text = page.locator(sel).first.text_content()")
    lines.append("                    if text:")
    lines.append("                        text = text.strip()")
    lines.append("                    else:")
    lines.append("                        text = ''")
    lines.append("                except Exception:")
    lines.append("                    text = ''")
    lines.append(
        "                rx = spec.get('regex') if isinstance(spec, dict) else None"
    )
    lines.append("                if rx:")
    lines.append("                    import re")
    lines.append("                    m = re.search(rx, text)")
    lines.append("                    if m:")
    lines.append(
        "                        text = m.group(1) if m.groups() else m.group(0)"
    )
    lines.append("                # Attempt number cast")
    lines.append("                try:")
    lines.append(
        "                    if text and all(c.isdigit() or c in ',. ' for c in text):"
    )
    lines.append(
        "                        num = int(''.join([c for c in text if c.isdigit()]))"
    )
    lines.append("                        result[field] = num")
    lines.append("                    else:")
    lines.append("                        result[field] = text")
    lines.append("                except Exception:")
    lines.append("                    result[field] = text")
    lines.append(
        "        (data_dir / f\"{JOB_ID}.json\").write_text(__import__('json').dumps(result), encoding='utf-8')"
    )
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
        plan, handle_cookie_banner=bool(options.get("handle_cookie_banner", False))
    )
    # Properly serialize the extraction_spec and escape backslashes for embedding in Python string
    extraction_spec = json.dumps(options.get("extraction_spec", {})).replace(
        "\\", "\\\\"
    )

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
    except Exception:
        pass
    return out_path
