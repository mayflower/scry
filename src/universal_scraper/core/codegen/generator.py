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

from ..ir.model import Click, Fill, Navigate, ScrapePlan, WaitFor


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
            lines.append('            print(f"Failed to click {step.selector}: {e}")')

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
                f'            page.locator("{step.selector}").wait_for(state="{state}", timeout=10000)'
            )
            lines.append("        except Exception as e:")
            lines.append(
                '            print(f"Timeout waiting for {step.selector}: {e}")'
            )
    # Extraction block
    lines.append("        # Extraction per spec")
    lines.append("        result = {}")
    lines.append("        for field, spec in EXTRACTION_SPEC.items():")
    lines.append("            sel = spec.get('selector')")
    lines.append("            if not sel: continue")
    lines.append("            try:")
    lines.append("                text = page.locator(sel).first.text_content()")
    lines.append("                if text:")
    lines.append("                    text = text.strip()")
    lines.append("                else:")
    lines.append("                    text = ''")
    lines.append("            except Exception:")
    lines.append("                text = ''")
    lines.append("            rx = spec.get('regex')")
    lines.append("            if rx:")
    lines.append("                import re")
    lines.append("                m = re.search(rx, text)")
    lines.append("                if m:")
    lines.append("                    text = m.group(1) if m.groups() else m.group(0)")
    lines.append("            # Attempt number cast")
    lines.append("            try:")
    lines.append(
        "                if text and all(c.isdigit() or c in ',. ' for c in text):"
    )
    lines.append(
        "                    num = int(''.join([c for c in text if c.isdigit()]))"
    )
    lines.append("                    result[field] = num")
    lines.append("                else:")
    lines.append("                    result[field] = text")
    lines.append("            except Exception:")
    lines.append("                result[field] = text")
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
    # Properly serialize the extraction_spec to avoid quote issues
    extraction_spec = json.dumps(options.get("extraction_spec", {}))

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
