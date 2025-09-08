from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from pathlib import Path

from playwright.sync_api import Page

from ..ir.model import Navigate, Click, Fill, WaitFor, PlanStep
from ...adapters.anthropic import complete_json


@dataclass
class ExplorationResult:
    steps: List[PlanStep]
    html_pages: List[str]
    screenshots: List[Path]
    urls: List[str]
    data: Optional[Dict[str, Any]] = None


def _summarize_dom(page: Page, max_items: int = 40) -> str:
    # Collect a compact summary: title, headings, inputs (names/placeholders), buttons, top anchors
    title = (page.title() or "").strip()
    headings = page.eval_on_selector_all(
        "h1, h2", "els => els.map(e=>e.textContent.trim()).filter(Boolean)"
    )
    inputs = page.eval_on_selector_all(
        "input, textarea",
        "els => els.map(e=>({ph:e.getAttribute('placeholder'),name:e.getAttribute('name'),label:e.getAttribute('aria-label')}))",
    )
    buttons = page.eval_on_selector_all(
        "button, [role=button]",
        "els => els.map(e=>({text:(e.innerText||'').trim(),name:e.getAttribute('name')})).filter(x=>x.text || x.name)",
    )
    anchors = page.eval_on_selector_all(
        "a",
        "els => els.map(e=>({text:(e.textContent||'').trim(),href:e.getAttribute('href')})).filter(x=>x.text && x.href)",
    )

    def limit(lst, n):
        return lst[:n] if isinstance(lst, list) else []

    headings = limit(headings, 6)
    inputs = limit(inputs, max_items)
    buttons = limit(buttons, max_items)
    anchors = limit(anchors, max_items)
    summary = {
        "title": title,
        "headings": headings,
        "inputs": inputs,
        "buttons": buttons,
        "anchors": anchors,
        "url": page.url,
    }
    # Keep it short
    import json

    return json.dumps(summary, ensure_ascii=False)


def _propose_next_action(
    nl_request: str, schema: Dict[str, Any], dom_summary_json: str
) -> Dict[str, Any]:
    system = (
        "You are an agent planner. Based on a compact DOM summary, propose the next action as JSON.\n"
        "Supported actions: navigate(url), click(selector), fill(selector,text), wait_for(selector,state), done().\n"
        "Selectors should be resilient and refer to visible elements (use roles, aria-labels, text).\n"
        "Output ONLY JSON with keys: action, selector, text, url, state. Omit unused keys.\n"
    )
    user = (
        f"goal: {nl_request}\n"
        f"schema: {schema}\n"
        f"dom_summary: {dom_summary_json}\n"
        'Respond with a single JSON object, e.g. {"action":"fill","selector":"input[placeholder~=\'Search\']","text":"employees"} or {"action":"done"}'
    )
    data, _ = complete_json(system, user, max_tokens=400)
    return data or {}


def agentic_explore(
    start_url: str,
    nl_request: str,
    schema: Dict[str, Any],
    page: Page,
    screenshots_dir: Path,
    html_dir: Path,
    job_id: str,
    max_steps: int = 12,
) -> ExplorationResult:
    steps: List[PlanStep] = []
    html_pages: List[str] = []
    screenshots: List[Path] = []
    urls: List[str] = []

    # First navigation
    page.goto(start_url)
    for step_index in range(1, max_steps + 1):
        # Snapshot artifacts
        out_path = screenshots_dir / f"step-{step_index}.png"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out_path), full_page=True)
        screenshots.append(out_path)

        html = page.content()
        html_pages.append(html)
        urls.append(page.url)
        html_dir.mkdir(parents=True, exist_ok=True)
        (html_dir / f"{job_id}-page-{step_index}.html").write_text(
            html, encoding="utf-8"
        )

        # Propose next action
        dom_summary = _summarize_dom(page)
        try:
            act = _propose_next_action(nl_request, schema, dom_summary)
        except Exception:
            break

        action = (act.get("action") or "").lower()
        if action in ("done", "stop", "finish"):
            break
        if action == "navigate" and act.get("url"):
            url = str(act["url"])  # type: ignore[index]
            steps.append(Navigate(url=url))
            page.goto(url)
            continue
        if action == "click" and act.get("selector"):
            sel = str(act["selector"])  # type: ignore[index]
            steps.append(Click(selector=sel))
            page.click(sel)
            continue
        if action == "fill" and act.get("selector"):
            sel = str(act["selector"])  # type: ignore[index]
            text = str(act.get("text", ""))
            steps.append(Fill(selector=sel, text=text))
            page.fill(sel, text)
            # Try pressing Enter in the same field to submit search if applicable
            try:
                page.press(sel, "Enter")
            except Exception:
                pass
            continue
        if action in ("wait_for", "waitfor", "wait") and act.get("selector"):
            sel = str(act["selector"])  # type: ignore[index]
            state = str(act.get("state", "visible"))
            steps.append(WaitFor(selector=sel, state=state))
            try:
                if state in ("visible", "hidden", "attached", "detached"):
                    page.wait_for_selector(sel, state=state)
                else:
                    page.wait_for_selector(sel)
            except Exception:
                pass
            continue
        # If invalid or unknown action, stop to avoid loops
        break

    return ExplorationResult(
        steps=steps, html_pages=html_pages, screenshots=screenshots, urls=urls
    )
