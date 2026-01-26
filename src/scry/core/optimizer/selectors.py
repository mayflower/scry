"""Resilient selector generation for web scraping.

This module provides utilities to generate multiple fallback selectors
for more reliable element identification.
"""

from __future__ import annotations

import re


def make_resilient_selector(selector: str, element_html: str | None = None) -> list[str]:
    """Generate multiple fallback selectors for resilience.

    Args:
        selector: Original CSS selector
        element_html: Optional HTML of the element for analysis

    Returns:
        List of selectors ordered by reliability
    """
    selectors = []

    # Always include the original
    if selector:
        selectors.append(selector)

    # If no HTML context, just return variations of the original
    if not element_html:
        return _generate_selector_variants(selector)

    # Extract attributes from HTML if provided
    attributes = _extract_attributes(element_html)

    # Priority 1: data-testid (most stable)
    if attributes.get("data-testid"):
        selectors.insert(0, f'[data-testid="{attributes["data-testid"]}"]')

    # Priority 2: id attribute
    if attributes.get("id"):
        selectors.insert(0, f"#{attributes['id']}")

    # Priority 3: aria-label
    if attributes.get("aria-label"):
        selectors.append(f'[aria-label="{attributes["aria-label"]}"]')

    # Priority 4: name attribute
    if attributes.get("name"):
        selectors.append(f'[name="{attributes["name"]}"]')

    # Add text-based XPath as fallback
    if attributes.get("text"):
        text = attributes["text"][:50]  # Limit text length
        selectors.append(f'//*[contains(text(), "{text}")]')

    # Remove duplicates while preserving order
    seen = set()
    unique_selectors = []
    for s in selectors:
        if s not in seen:
            seen.add(s)
            unique_selectors.append(s)

    return unique_selectors


def _generate_selector_variants(selector: str) -> list[str]:
    """Generate variations of a selector for fallback.

    Args:
        selector: Original CSS selector

    Returns:
        List of selector variants
    """
    variants = [selector]

    # If it's a class selector, try without pseudo-classes
    if "." in selector and ":" in selector:
        base = selector.split(":")[0]
        variants.append(base)

    # If it's a complex selector, try simplifying
    if " > " in selector:
        # Try without direct child requirement
        variants.append(selector.replace(" > ", " "))

    # If it has multiple classes, try with fewer
    if selector.count(".") > 1:
        # Keep only the first class
        match = re.match(r"^([^.]+\.[^.\s\[]+)", selector)
        if match:
            variants.append(match.group(1))

    return variants


def _extract_attributes(html: str) -> dict:
    """Extract useful attributes from an HTML element string.

    Args:
        html: HTML string of the element

    Returns:
        Dictionary of extracted attributes
    """
    attributes = {}

    # Extract data-testid
    match = re.search(r'data-testid=["\'](.*?)["\']', html)
    if match:
        attributes["data-testid"] = match.group(1)

    # Extract id
    match = re.search(r'\bid=["\'](.*?)["\']', html)
    if match:
        attributes["id"] = match.group(1)

    # Extract aria-label
    match = re.search(r'aria-label=["\'](.*?)["\']', html)
    if match:
        attributes["aria-label"] = match.group(1)

    # Extract name
    match = re.search(r'\bname=["\'](.*?)["\']', html)
    if match:
        attributes["name"] = match.group(1)

    # Extract text content (simplified)
    match = re.search(r">([^<]+)<", html)
    if match:
        text = match.group(1).strip()
        if text:
            attributes["text"] = text

    return attributes


def improve_selector_resilience(selector: str) -> str:
    """Improve a single selector for better resilience.

    Args:
        selector: Original CSS selector

    Returns:
        Improved selector or original if can't improve
    """
    # If already using stable attributes, keep it
    stable_attributes = ["data-testid=", "#", "aria-label=", "name="]
    if any(attr in selector for attr in stable_attributes):
        return selector

    # Remove brittle position-based selectors
    selector = re.sub(r":nth-child\(\d+\)", "", selector)
    selector = re.sub(r":first-child", "", selector)
    selector = re.sub(r":last-child", "", selector)

    # Simplify overly specific selectors
    if selector.count(" ") > 3:
        # Keep only the last 2 levels
        parts = selector.split(" ")
        selector = " ".join(parts[-2:])

    return selector.strip()


def generate_fallback_code(selectors: list[str], action: str = "click") -> str:
    """Generate Python code with fallback selectors.

    Args:
        selectors: List of fallback selectors
        action: Action to perform (click, fill, etc.)

    Returns:
        Python code string with fallback logic
    """
    if not selectors:
        return ""

    lines = []
    lines.append("element = None")
    lines.append("for selector in [")
    for selector in selectors:
        lines.append(f'    "{selector}",')
    lines.append("]:")
    lines.append("    try:")
    lines.append("        loc = page.locator(selector)")
    lines.append("        if loc.count() > 0:")
    lines.append("            element = loc.first")
    lines.append("            break")
    lines.append("    except:")
    lines.append("        continue")
    lines.append("")
    lines.append("if element:")

    if action == "click":
        lines.append("    element.click()")
    elif action == "fill":
        lines.append("    element.fill(text)")
    elif action == "wait":
        lines.append("    element.wait_for()")
    else:
        lines.append(f"    # Perform {action}")

    lines.append("else:")
    lines.append('    print("No element found with any selector")')

    return "\n".join(lines)
